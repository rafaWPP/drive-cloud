"""Opt-in, one-way desktop folder backup to the user's own Telegram channel.

A local deletion NEVER deletes anything from the Telegram catalog. Replaced
versions go to the catalog trash; their Telegram messages remain untouched.
Automatic work is disabled until the user explicitly enables it per folder.
"""
import asyncio
import mimetypes
import os
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from sync_reconcile import (remote_tree, safe_relative, decision, get_remote_file,
                            install_download, MAX_DOWNLOADS_PER_RUN)

from storage_api import MAX_SIZE, connection, channel_id
from catalog_merge import merge_catalog
from catalog_telegram import MARKER, MAX_SNAPSHOT_BYTES, decode_catalog, send_catalog_snapshot

MAX_SCAN_FILES = 10000
MAX_UPLOADS_PER_RUN = 3
IGNORE_DIRS = {"node_modules", ".git", ".venv", "__pycache__", ".cache"}
IGNORED_FILES = {".DS_Store", "Thumbs.db"}
FORBIDDEN_TOP = {"/", "/proc", "/sys", "/dev", "/etc"}


class FolderRequest(BaseModel):
    path: str = Field(min_length=2, max_length=4096)
    remote_root_id: str | None = None


class AutoRequest(BaseModel):
    enabled: bool


class SyncModeRequest(BaseModel):
    mode: Literal["backup", "two-way"]


def ensure_schema(db: sqlite3.Connection):
    db.execute("""CREATE TABLE IF NOT EXISTS sync_folders(
        id TEXT PRIMARY KEY, account TEXT NOT NULL, path TEXT NOT NULL,
        root_node TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 0,
        last_run INTEGER, last_error TEXT,
        UNIQUE(account,path))""")
    db.execute("""CREATE TABLE IF NOT EXISTS sync_entries(
        folder_id TEXT NOT NULL, rel_path TEXT NOT NULL,
        node_id TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
        PRIMARY KEY(folder_id,rel_path))""")
    cols = {item[1] for item in db.execute("PRAGMA table_info(sync_folders)")}
    if "mode" not in cols:
        db.execute("ALTER TABLE sync_folders ADD COLUMN mode TEXT NOT NULL DEFAULT 'backup'")
    db.execute("""CREATE TABLE IF NOT EXISTS sync_remote_seen(
        folder_id TEXT NOT NULL, rel_path TEXT NOT NULL,
        node_id TEXT NOT NULL, outcome TEXT NOT NULL, created INTEGER NOT NULL,
        PRIMARY KEY(folder_id,rel_path,node_id))""")
    db.execute("""CREATE TABLE IF NOT EXISTS sync_catalog_seen(
        account TEXT NOT NULL, channel TEXT NOT NULL, message_id INTEGER NOT NULL,
        imported_at INTEGER NOT NULL,
        PRIMARY KEY(account,channel,message_id))""")
    db.execute("CREATE INDEX IF NOT EXISTS sync_folders_account ON sync_folders(account)")


def source_root(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        raise HTTPException(422, "Selecione uma pasta absoluta do computador.")
    if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
        raise HTTPException(422, "Atalhos simbólicos não podem ser sincronizados.")
    try:
        root = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise HTTPException(422, "Pasta inacessível ou não encontrada.") from exc
    if not root.is_dir() or str(root) in FORBIDDEN_TOP or root == Path(root.anchor):
        raise HTTPException(422, "Selecione uma pasta de documentos, não um diretório do sistema.")
    if root.is_symlink():
        raise HTTPException(422, "Atalhos simbólicos não podem ser sincronizados.")
    return root


def scan_folder(root: Path):
    """Enumerate regular, non-symlink files with a bounded memory footprint."""
    items = []
    oversized = 0
    try:
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS and not (Path(current) / d).is_symlink())
            for name in sorted(files):
                if name in IGNORED_FILES or name.endswith((".tmp", ".part", ".swp")):
                    continue
                path = Path(current) / name
                if path.is_symlink():
                    continue
                try:
                    st = path.stat()
                except OSError:
                    continue
                if not path.is_file():
                    continue
                if st.st_size > MAX_SIZE:
                    oversized += 1
                    continue
                items.append((path.relative_to(root).as_posix(), st.st_size, st.st_mtime_ns))
                if len(items) > MAX_SCAN_FILES:
                    raise HTTPException(413, "A pasta excede 10 mil arquivos. Selecione pastas menores.")
    except OSError as exc:
        raise HTTPException(422, "Não foi possível examinar a pasta selecionada.") from exc
    return items, oversized


def ensure_remote_folder(db, account, parent_id, name, timestamp):
    existing = db.execute(
        "SELECT id FROM nodes WHERE account=? AND parent IS ? AND name=? "
        "AND kind='folder' AND trashed=0 ORDER BY created LIMIT 1",
        (account, parent_id, name)).fetchone()
    if existing:
        return existing["id"]
    node = str(uuid.uuid4())
    db.execute(
        "INSERT INTO nodes (id,account,kind,parent,name,created) VALUES (?,?,?,?,?,?)",
        (node, account, "folder", parent_id, name, timestamp),
    )
    return node


def pending_files(db, folder, files):
    tracked = {
        r["rel_path"]: (r["size"], r["mtime_ns"])
        for r in db.execute("SELECT rel_path,size,mtime_ns FROM sync_entries WHERE folder_id=?", (folder["id"],))
    }
    return [(rel, size, mtime) for rel, size, mtime in files
            if tracked.get(rel) != (size, mtime)]


def build_folder_sync_router(authorized_account, channel_links, lock):
    router = APIRouter(prefix="/api/sync")
    active_runs = set()

    async def refresh_catalog_impl(client, account, channel):
        """Append-only union of bounded channel snapshots; must hold account lock."""
        messages = []
        async for message in client.iter_messages(channel, search=MARKER, limit=121):
            if message.message == MARKER and message.file:
                messages.append(message)
        if len(messages) > 120:
            raise HTTPException(409, "Histórico do catálogo acima do limite de reconciliação. Faça cópias antes de continuar.")
        total_imported = 0
        conflicts = 0
        processed = 0
        for message in reversed(messages):
            with connection() as db:
                ensure_schema(db)
                previously = db.execute(
                    "SELECT 1 FROM sync_catalog_seen WHERE account=? AND channel=? AND message_id=?",
                    (account, str(channel), message.id),
                ).fetchone()
            if previously:
                continue
            if not message.file.size or message.file.size > MAX_SNAPSHOT_BYTES:
                raise HTTPException(413, "Snapshot remoto ultrapassa o limite de 2 MB.")
            try:
                raw = await client.download_media(message, file=bytes)
            except Exception as exc:
                raise HTTPException(502, "Falha ao atualizar metadados do Telegram.") from exc
            if not isinstance(raw, bytes):
                raise HTTPException(502, "Falha ao receber catálogo remoto.")
            payload = decode_catalog(raw, account, channel)
            with connection() as db:
                ensure_schema(db)
                result = merge_catalog(db, payload, account, channel)
                db.execute(
                    "INSERT OR IGNORE INTO sync_catalog_seen(account,channel,message_id,imported_at)"
                    " VALUES (?,?,?,?)",
                    (account, str(channel), message.id, int(time.time())),
                )
            total_imported += result["imported"]
            conflicts += result["metadata_differences_preserved"]
            processed += 1
        return {"snapshots_checked": len(messages), "snapshots_processed": processed,
                "items_added": total_imported, "metadata_differences_preserved": conflicts}

    @router.post("/catalog/refresh")
    async def refresh_catalog():
        async with lock:
            client, account = await authorized_account()
            channel = channel_id(channel_links, account)
            result = await refresh_catalog_impl(client, account, channel)
            if result["items_added"]:
                # Propagate the safe union to newer devices; never replace a snapshot.
                with connection() as db:
                    await send_catalog_snapshot(client, db, account, channel)
            return result

    @router.post("/folders/preview")
    async def preview_folder(body: FolderRequest):
        root = source_root(body.path)
        files, oversized = await asyncio.to_thread(scan_folder, root)
        # Never reveal the contents of any file or write them on preview.
        return {"path": str(root), "files": len(files), "bytes": sum(x[1] for x in files),
                "over_limit": oversized, "max_file_bytes": MAX_SIZE}

    @router.get("/remote-roots")
    async def remote_roots():
        """Only active top-level backup roots from the authenticated account."""
        async with lock:
            _, account = await authorized_account()
            with connection() as db:
                roots = db.execute(
                    "SELECT id,name,created FROM nodes WHERE account=? AND parent IS NULL "
                    "AND kind='folder' AND trashed=0 AND name LIKE 'Backup • %' ORDER BY created DESC",
                    (account,),
                ).fetchall()
            return {"roots": [dict(root) for root in roots]}

    @router.get("/folders")
    async def list_folders():
        async with lock:
            _, account = await authorized_account()
            with connection() as db:
                ensure_schema(db)
                rows = db.execute(
                     "SELECT id,path,enabled,last_run,last_error,mode,root_node FROM sync_folders "
                    "WHERE account=? ORDER BY path", (account,)).fetchall()
            return {"folders": [dict(row) for row in rows]}

    @router.post("/folders")
    async def add_folder(body: FolderRequest):
        root = source_root(body.path)
        async with lock:
            _, account = await authorized_account()
            channel_id(channel_links, account)
            with connection() as db:
                ensure_schema(db)
                existing = db.execute("SELECT id FROM sync_folders WHERE account=? AND path=?",
                                      (account, str(root))).fetchone()
                if existing:
                    return {"id": existing["id"], "already_exists": True}
                timestamp = int(time.time() * 1000)
                folder_id = str(uuid.uuid4())
                if body.remote_root_id:
                    try:
                        requested_id = str(uuid.UUID(body.remote_root_id))
                    except (TypeError, ValueError, AttributeError) as exc:
                        raise HTTPException(422, "Pasta remota inválida.") from exc
                    found = db.execute(
                        "SELECT id,name FROM nodes WHERE id=? AND account=? AND kind='folder' "
                        "AND parent IS NULL AND trashed=0",
                        (requested_id, account),
                    ).fetchone()
                    if not found or not found["name"].startswith("Backup • "):
                        raise HTTPException(409, "Pasta remota não pertence a este Drive.")
                    node = found["id"]
                else:
                    # Creating a new backup must never modify another root.
                    node = str(uuid.uuid4())
                    db.execute(
                        "INSERT INTO nodes (id,account,kind,parent,name,created) VALUES (?,?,?,?,?,?)",
                        (node, account, "folder", None, "Backup • " + root.name[:160], timestamp),
                    )
                db.execute(
                    "INSERT INTO sync_folders (id,account,path,root_node) VALUES (?,?,?,?)",
                    (folder_id, account, str(root), node),
                )
            return {"id": folder_id, "already_exists": False, "enabled": False}

    @router.post("/folders/{folder_id}/preview")
    async def preview_pending(folder_id: str):
        async with lock:
            _, account = await authorized_account()
            with connection() as db:
                ensure_schema(db)
                folder = db.execute("SELECT * FROM sync_folders WHERE id=? AND account=?",
                                    (folder_id, account)).fetchone()
                if not folder:
                    raise HTTPException(404, "Pasta de sincronização não encontrada.")
                root = source_root(folder["path"])
                files, oversized = await asyncio.to_thread(scan_folder, root)
                pending = pending_files(db, folder, files)
                return {"pending": len(pending), "pending_bytes": sum(x[1] for x in pending),
                        "over_limit": oversized, "batch_limit": MAX_UPLOADS_PER_RUN,
                        "deletions_ignored": True}

    async def perform_sync(folder_id: str):
        if folder_id in active_runs:
            raise HTTPException(409, "Esta pasta já está sendo sincronizada.")
        active_runs.add(folder_id)
        try:
            async with lock:
                client, account = await authorized_account()
                telegram_channel = channel_id(channel_links, account)
                with connection() as db:
                    ensure_schema(db)
                    folder = db.execute("SELECT * FROM sync_folders WHERE id=? AND account=?",
                                        (folder_id, account)).fetchone()
                    if not folder:
                        raise HTTPException(404, "Pasta de sincronização não encontrada.")
                    root = source_root(folder["path"])
                    files, oversized = await asyncio.to_thread(scan_folder, root)
                    pending = pending_files(db, folder, files)
                sent = 0
                for rel, size, mtime in pending[:MAX_UPLOADS_PER_RUN]:
                    original = root / rel
                    if original.is_symlink() or any(parent.is_symlink() for parent in original.parents if parent != root):
                        continue
                    try:
                        if not original.resolve(strict=True).is_relative_to(root):
                            continue
                    except OSError:
                        continue
                    before = original.stat()
                    if before.st_size != size or before.st_mtime_ns != mtime:
                        continue
                    try:
                        message = await client.send_file(
                            telegram_channel, str(original), force_document=True,
                            caption="Drive Cloud • backup de pasta",
                            part_size_kb=512,
                        )
                    except Exception as exc:
                        with connection() as db:
                            ensure_schema(db)
                            db.execute("UPDATE sync_folders SET last_error=? WHERE id=? AND account=?",
                                       ("Falha no upload: " + type(exc).__name__, folder_id, account))
                        raise HTTPException(502, "Falha ao enviar um arquivo ao Telegram.") from exc
                    after = original.stat()
                    if after.st_size != size or after.st_mtime_ns != mtime:
                        # A concurrently modified file will be reconsidered on next run.
                        # The Telegram message is retained; never delete remote data automatically.
                        continue
                    with connection() as db:
                        ensure_schema(db)
                        parent = folder["root_node"]
                        timestamp = int(time.time() * 1000)
                        for segment in Path(rel).parts[:-1]:
                            parent = ensure_remote_folder(db, account, parent, segment, timestamp)
                        new_id = str(uuid.uuid4())
                        db.execute(
                            "INSERT INTO nodes (id,account,kind,parent,name,size,mime,message_id,created)"
                            " VALUES (?,?,?,?,?,?,?,?,?)",
                            (new_id, account, "file", parent, Path(rel).name, size,
                             mimetypes.guess_type(rel)[0] or "application/octet-stream",
                             message.id, timestamp),
                        )
                        old = db.execute(
                            "SELECT node_id FROM sync_entries WHERE folder_id=? AND rel_path=?",
                            (folder_id, rel)).fetchone()
                        db.execute(
                            "INSERT INTO sync_entries(folder_id,rel_path,node_id,size,mtime_ns)"
                            " VALUES (?,?,?,?,?) ON CONFLICT(folder_id,rel_path) DO UPDATE SET "
                            "node_id=excluded.node_id,size=excluded.size,mtime_ns=excluded.mtime_ns",
                            (folder_id, rel, new_id, size, mtime),
                        )
                        # Old revision remains recoverable from Trash with its original message intact.
                        if old:
                            db.execute("UPDATE nodes SET trashed=1 WHERE id=? AND account=?",
                                       (old["node_id"], account))
                    sent += 1
                with connection() as db:
                    ensure_schema(db)
                    db.execute("UPDATE sync_folders SET last_run=?,last_error=NULL WHERE id=? AND account=?",
                               (int(time.time()), folder_id, account))
                snapshot_saved = False
                if sent:
                    try:
                        with connection() as db:
                            await send_catalog_snapshot(client, db, account, telegram_channel)
                        snapshot_saved = True
                    except HTTPException:
                        # Files remain saved on Telegram, even if metadata publishing fails.
                        snapshot_saved = False
                return {"sent": sent, "remaining_estimate": max(0, len(pending) - sent),
                        "over_limit": oversized, "deletions_ignored": True,
                        "catalog_snapshot_saved": snapshot_saved}
        finally:
            active_runs.discard(folder_id)

    @router.post("/folders/{folder_id}/run")
    async def run_sync(folder_id: str):
        async with lock:
            _, account = await authorized_account()
            with connection() as db:
                ensure_schema(db)
                folder = db.execute(
                    "SELECT mode FROM sync_folders WHERE id=? AND account=?", (folder_id, account)
                ).fetchone()
                if not folder:
                    raise HTTPException(404, "Pasta de sincronização não encontrada.")
                mode = folder["mode"]
        pulled = await perform_pull(folder_id) if mode == "two-way" else None
        uploaded = await perform_sync(folder_id)
        if pulled is not None:
            uploaded["remote"] = pulled
        return uploaded

    async def perform_pull(folder_id: str, dry_run: bool = False):
        """Reconcile active Telegram versions without overwriting PC files."""
        if folder_id in active_runs:
            raise HTTPException(409, "Esta pasta já está sendo sincronizada.")
        active_runs.add(folder_id)
        try:
            async with lock:
                client, account = await authorized_account()
                channel = channel_id(channel_links, account)
                if not dry_run:
                    await refresh_catalog_impl(client, account, channel)
                with connection() as db:
                    ensure_schema(db)
                    folder = db.execute("SELECT * FROM sync_folders WHERE id=? AND account=?",
                                        (folder_id, account)).fetchone()
                    if not folder:
                        raise HTTPException(404, "Pasta de sincronização não encontrada.")
                    root = source_root(folder["path"])
                    remote = remote_tree(db, account, folder["root_node"])
                    tracked = {
                        r["rel_path"]: r["node_id"] for r in db.execute(
                            "SELECT rel_path,node_id FROM sync_entries WHERE folder_id=?", (folder_id,)
                        )
                    }
                    seen = {
                        (r["rel_path"], r["node_id"]) for r in db.execute(
                            "SELECT rel_path,node_id FROM sync_remote_seen WHERE folder_id=?", (folder_id,)
                        )
                    }
                actions = []
                over_limit = 0
                for rel, item in sorted(remote.items()):
                    if item["size"] > MAX_SIZE:
                        over_limit += 1
                        continue
                    destination = safe_relative(root, tuple(rel.split("/")))
                    classification = decision(destination, item["id"], tracked.get(rel))
                    if classification == "unsafe":
                        raise HTTPException(409, "Caminho local inacessível: " + rel)
                    if classification == "known" or (rel, item["id"]) in seen:
                        continue
                    actions.append((rel, item, destination))
                if dry_run:
                    return {
                        "pending": len(actions),
                        "conflicts_possible": sum(1 for _, _, dest in actions if dest.exists()),
                        "over_limit": over_limit,
                        "batch_limit": MAX_DOWNLOADS_PER_RUN,
                        "files_preserved": True,
                    }
                results = {"downloaded": 0, "identical": 0, "conflicts": 0, "over_limit": over_limit}
                for rel, item, destination in actions[:MAX_DOWNLOADS_PER_RUN]:
                    temp = None
                    try:
                        temp = await get_remote_file(client, channel, item)
                        outcome, installed = await asyncio.to_thread(
                            install_download, temp, destination, root, item["id"]
                        )
                    except HTTPException:
                        raise
                    except Exception as exc:
                        raise HTTPException(502, "Falha ao recuperar arquivo do Telegram: " + type(exc).__name__) from exc
                    finally:
                        if temp is not None:
                            temp.unlink(missing_ok=True)
                    if outcome == "downloaded":
                        results["downloaded"] += 1
                    elif outcome == "identical":
                        results["identical"] += 1
                    else:
                        results["conflicts"] += 1
                    with connection() as db:
                        ensure_schema(db)
                        db.execute(
                            "INSERT OR IGNORE INTO sync_remote_seen"
                            "(folder_id,rel_path,node_id,outcome,created) VALUES (?,?,?,?,?)",
                            (folder_id, rel, item["id"], outcome, int(time.time())),
                        )
                        if outcome in ("downloaded", "identical"):
                            stat = installed.stat()
                            db.execute(
                                "INSERT INTO sync_entries(folder_id,rel_path,node_id,size,mtime_ns)"
                                " VALUES (?,?,?,?,?) ON CONFLICT(folder_id,rel_path) DO UPDATE SET "
                                "node_id=excluded.node_id,size=excluded.size,mtime_ns=excluded.mtime_ns",
                                (folder_id, rel, item["id"], stat.st_size, stat.st_mtime_ns),
                            )
                results["remaining_estimate"] = max(0, len(actions) - MAX_DOWNLOADS_PER_RUN)
                return results
        finally:
            active_runs.discard(folder_id)

    @router.post("/folders/{folder_id}/remote/preview")
    async def preview_remote(folder_id: str):
        return await perform_pull(folder_id, dry_run=True)

    @router.post("/folders/{folder_id}/pull")
    async def pull_remote(folder_id: str):
        return await perform_pull(folder_id)

    @router.post("/folders/{folder_id}/mode")
    async def set_mode(folder_id: str, body: SyncModeRequest):
        """Two-way mode is an explicit opt-in, never enabled by migration."""
        async with lock:
            _, account = await authorized_account()
            with connection() as db:
                ensure_schema(db)
                cursor = db.execute(
                    "UPDATE sync_folders SET mode=? WHERE id=? AND account=?",
                    (body.mode, folder_id, account),
                )
                if not cursor.rowcount:
                    raise HTTPException(404, "Pasta de sincronização não encontrada.")
        return {"mode": body.mode}

    @router.post("/folders/{folder_id}/automatic")
    async def set_automatic(folder_id: str, body: AutoRequest):
        async with lock:
            _, account = await authorized_account()
            with connection() as db:
                ensure_schema(db)
                result = db.execute(
                    "UPDATE sync_folders SET enabled=? WHERE id=? AND account=?",
                    (int(body.enabled), folder_id, account),
                )
                if not result.rowcount:
                    raise HTTPException(404, "Pasta de sincronização não encontrada.")
            return {"enabled": body.enabled}

    @router.delete("/folders/{folder_id}")
    async def detach_folder(folder_id: str):
        """Stop monitoring this directory without deleting any Telegram content."""
        async with lock:
            _, account = await authorized_account()
            with connection() as db:
                ensure_schema(db)
                match = db.execute(
                    "SELECT id FROM sync_folders WHERE id=? AND account=?",
                    (folder_id, account),
                ).fetchone()
                if not match:
                    raise HTTPException(404, "Pasta de sincronização não encontrada.")
                db.execute("DELETE FROM sync_remote_seen WHERE folder_id=?", (folder_id,))
                db.execute("DELETE FROM sync_entries WHERE folder_id=?", (folder_id,))
                db.execute("DELETE FROM sync_folders WHERE id=? AND account=?",
                           (folder_id, account))
            return {"removed": True, "telegram_files_preserved": True}

    async def scheduler():
        # Initial delay avoids unexpected uploads just after launch.
        while True:
            try:
                await asyncio.sleep(120)
                async with lock:
                    _, account = await authorized_account()
                    with connection() as db:
                        ensure_schema(db)
                        ids = [r["id"] for r in db.execute(
                            "SELECT id FROM sync_folders WHERE account=? AND enabled=1", (account,))]
                for folder_id in ids:
                    try:
                        async with lock:
                            _, current_account = await authorized_account()
                            with connection() as db:
                                ensure_schema(db)
                                current = db.execute(
                                    "SELECT mode FROM sync_folders WHERE id=? AND account=?",
                                    (folder_id, current_account),
                                ).fetchone()
                        if current:
                            await run_sync(folder_id)
                    except (HTTPException, OSError):
                        continue  # A missing/unmounted directory never triggers remote deletion.
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(30)

    return router, scheduler
