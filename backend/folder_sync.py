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

from storage_api import MAX_SIZE, DB_PATH, connection, channel_id
from telegram_limits import upload_limit
from multipart_telegram import send_document, MAX_FILE_BYTES
from catalog_merge import merge_catalog
from catalog_telegram import MARKER, MAX_SNAPSHOT_BYTES, decode_catalog, send_catalog_snapshot

MAX_SCAN_FILES = 10000
MAX_UPLOADS_PER_RUN = 3
IGNORE_DIRS = {"node_modules", ".git", ".venv", "__pycache__", ".cache",
               ".ssh", ".gnupg", ".config", ".local", "AppData",
               "Application Data", "System Volume Information", "$RECYCLE.BIN"}
IGNORED_FILES = {".DS_Store", "Thumbs.db"}
FORBIDDEN_TOP = {"/", "/proc", "/sys", "/dev", "/etc"}


class FolderRequest(BaseModel):
    path: str = Field(min_length=2, max_length=4096)
    remote_root_id: str | None = None
    remote_folder_name: str | None = Field(default=None, max_length=180)
    mode: Literal["backup", "two-way"] = "backup"
    automatic: bool = False


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
    if root.is_relative_to(DB_PATH.parent.resolve()):
        raise HTTPException(422, "A pasta de dados internos do aplicativo não pode ser sincronizada.")
    return root


def scan_folder(root: Path, max_size: int = MAX_FILE_BYTES):
    """Enumerate regular, non-symlink files with a bounded memory footprint."""
    items = []
    oversized = 0
    try:
        for current, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d.casefold() not in {n.casefold() for n in IGNORE_DIRS} and not (Path(current) / d).is_symlink())
            for name in sorted(files):
                if name.startswith(".") or name in IGNORED_FILES or name.endswith((".tmp", ".part", ".swp")):
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
                if st.st_size > max_size:
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


def remote_folder_path(db, account, folder_id):
    """Validate that the selected Drive folder and every ancestor are active.

    Never create or upload into a trashed or detached folder. UUIDs are
    validated at the API edge; all lookups are scoped to the Telegram account.
    """
    names = []
    visited = set()
    current = folder_id
    while current is not None:
        if current in visited or len(visited) >= 128:
            raise HTTPException(409, "O caminho da pasta do Drive contém um vínculo inválido.")
        visited.add(current)
        node = db.execute(
            "SELECT parent,name,kind,trashed FROM nodes WHERE account=? AND id=?",
            (account, current),
        ).fetchone()
        if not node or node["kind"] != "folder" or node["trashed"]:
            raise HTTPException(409, "A pasta escolhida no Meu Drive foi removida ou está na lixeira.")
        names.append(node["name"])
        current = node["parent"]
    return " / ".join(reversed(names))


def list_remote_folders(db, account):
    """List the real folder tree in Meu Drive, not only backup-named roots."""
    rows = db.execute(
        "SELECT id,parent,name,created,trashed FROM nodes WHERE account=? AND kind='folder'",
        (account,),
    ).fetchall()
    by_id = {row["id"]: row for row in rows}
    cache = {}
    def resolve(folder_id, trail):
        if folder_id in cache:
            return cache[folder_id]
        if folder_id in trail or len(trail) >= 128:
            return None
        node = by_id.get(folder_id)
        if not node or node["trashed"]:
            return None
        parent = node["parent"]
        if parent is None:
            full = node["name"]
        else:
            base = resolve(parent, trail | {folder_id})
            if base is None:
                return None
            full = base + " / " + node["name"]
        cache[folder_id] = full
        return full
    options = []
    for row in rows:
        path = resolve(row["id"], set())
        if path is not None:
            options.append({
                "id": row["id"], "name": row["name"],
                "path": path, "created": row["created"],
            })
    return sorted(options, key=lambda item: (item["path"].casefold(), item["id"]))


def new_remote_folder_name(name):
    if not isinstance(name, str):
        raise HTTPException(422, "Informe o nome da pasta nova no Meu Drive.")
    name = name.strip()
    if (not name or name in (".", "..") or len(name) > 180
        or any(char == "/" or ord(char) in (0, 92) for char in name)
        or any(ord(char) < 32 for char in name)):
        raise HTTPException(422, "Nome inválido para a nova pasta no Meu Drive.")
    return name


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

    @router.get("/activity")
    async def activity():
        """Non-blocking activity probe.

        Folder listing uses the account lock, held throughout Telegram uploads.
        Returning only active folder IDs here lets the desktop keep its last
        known rows visible and report live activity without blocking on upload.
        This route is reachable only through the loopback-only application.
        """
        return {"active_folder_ids": sorted(active_runs)}


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
        async with lock:
            client, _ = await authorized_account()
            max_size = MAX_FILE_BYTES
        files, oversized = await asyncio.to_thread(scan_folder, root, max_size)
        # Never reveal the contents of any file or write them on preview.
        return {"path": str(root), "files": len(files), "bytes": sum(x[1] for x in files),
                "over_limit": oversized, "max_file_bytes": max_size}

    @router.get("/remote-folders")
    async def remote_folders():
        """Show all existing folders in Meu Drive, including nested folders."""
        async with lock:
            _, account = await authorized_account()
            channel_id(channel_links, account)
            with connection() as db:
                ensure_schema(db)
                options = list_remote_folders(db, account)
                mapped = {
                    row["root_node"]: row["path"] for row in db.execute(
                        "SELECT path,root_node FROM sync_folders WHERE account=?", (account,)
                    )
                }
            return {"folders": [{**item, "linked_local_path": mapped.get(item["id"])}
                                for item in options]}

    @router.get("/remote-roots")
    async def remote_roots():
        """Backward-compatible legacy backup picker, not used by new desktop UI."""
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
                output = []
                for row in rows:
                    item = dict(row)
                    try:
                        item["remote_path"] = remote_folder_path(db, account, row["root_node"])
                        item["remote_available"] = True
                    except HTTPException:
                        item["remote_path"] = "Pasta do Drive indisponível"
                        item["remote_available"] = False
                    output.append(item)
            return {"folders": output}

    @router.post("/folders")
    async def add_folder(body: FolderRequest):
        root = source_root(body.path)
        async with lock:
            client, account = await authorized_account()
            channel = channel_id(channel_links, account)
            with connection() as db:
                ensure_schema(db)
                existing = db.execute("SELECT id FROM sync_folders WHERE account=? AND path=?",
                                      (account, str(root))).fetchone()
                if existing:
                    return {"id": existing["id"], "already_exists": True}
                timestamp = int(time.time() * 1000)
                folder_id = str(uuid.uuid4())
                if bool(body.remote_root_id) == bool(body.remote_folder_name):
                    raise HTTPException(422, "Escolha uma pasta existente no Meu Drive ou informe o nome de uma nova.")
                if body.remote_root_id:
                    try:
                        requested_id = str(uuid.UUID(body.remote_root_id))
                    except (TypeError, ValueError, AttributeError) as exc:
                        raise HTTPException(422, "Pasta do Meu Drive inválida.") from exc
                    remote_path = remote_folder_path(db, account, requested_id)
                    node = requested_id
                else:
                    name = new_remote_folder_name(body.remote_folder_name)
                    duplicate = db.execute(
                        "SELECT id FROM nodes WHERE account=? AND parent IS NULL "
                        "AND kind='folder' AND trashed=0 AND name=?",
                        (account, name),
                    ).fetchone()
                    if duplicate:
                        raise HTTPException(409, "Já existe uma pasta com esse nome na raiz do Meu Drive. Selecione-a na lista.")
                    node = str(uuid.uuid4())
                    db.execute(
                        "INSERT INTO nodes (id,account,kind,parent,name,created) VALUES (?,?,?,?,?,?)",
                        (node, account, "folder", None, name, timestamp),
                    )
                    remote_path = name
                conflict = db.execute(
                    "SELECT path FROM sync_folders WHERE account=? AND root_node=?",
                    (account, node),
                ).fetchone()
                if conflict:
                    raise HTTPException(
                        409, "Essa pasta do Meu Drive já está vinculada a outra pasta deste computador: " + conflict["path"],
                    )
                db.execute(
                    "INSERT INTO sync_folders (id,account,path,root_node,mode,enabled) VALUES (?,?,?,?,?,?)",
                    (folder_id, account, str(root), node, body.mode, int(body.automatic)),
                )
            # A folder created from this PC must also become discoverable by
            # the other devices. On failure, preserve local data and report
            # that the portable Telegram catalog still needs saving.
            catalog_snapshot_saved = True
            if not body.remote_root_id:
                try:
                    with connection() as db:
                        await send_catalog_snapshot(client, db, account, channel)
                except Exception:
                    catalog_snapshot_saved = False
            return {"id": folder_id, "already_exists": False,
                    "remote_path": remote_path, "mode": body.mode,
                    "catalog_snapshot_saved": catalog_snapshot_saved,
                    "enabled": body.automatic}

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
                max_size = MAX_FILE_BYTES
                files, oversized = await asyncio.to_thread(scan_folder, root, max_size)
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
                    remote_folder_path(db, account, folder["root_node"])
                    root = source_root(folder["path"])
                    max_size = MAX_FILE_BYTES
                    files, oversized = await asyncio.to_thread(scan_folder, root, max_size)
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
                        message = await send_document(
                            client, telegram_channel, original, Path(rel).name,
                            mimetypes.guess_type(rel)[0] or "application/octet-stream",
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
                    remote_folder_path(db, account, folder["root_node"])
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
                    if item["size"] > MAX_FILE_BYTES:
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
