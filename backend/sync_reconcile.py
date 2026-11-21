"""Non-destructive Telegram-to-PC reconciliation helpers.

A remote file is *never* allowed to replace an existing local file. When
names conflict, retain the PC version and save a clearly labeled Telegram copy.
The caller must already have an authenticated account and a verified root.
"""
import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException

from storage_api import DB_PATH, MAX_SIZE
from multipart_telegram import MAX_FILE_BYTES, download_document

MAX_REMOTE_ITEMS = 10000
MAX_DOWNLOADS_PER_RUN = 3


def safe_segment(segment):
    """Cross-platform name validation for data derived from remote catalogs."""
    if not isinstance(segment, str) or not segment or segment in (".", ".."):
        raise HTTPException(422, "Caminho remoto inválido.")
    if len(segment) > 180 or segment.endswith((" ", ".")):
        raise HTTPException(422, "Nome remoto não é seguro para o sistema.")
    if any(ord(ch) < 32 or ch in '/\\:<>|?*"\x00' for ch in segment):
        raise HTTPException(422, "Nome de arquivo remoto inválido.")
    if segment.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        raise HTTPException(422, "Nome reservado pelo sistema.")
    return segment


def safe_relative(root, parts):
    if not parts:
        raise HTTPException(422, "Arquivo remoto sem caminho.")
    root = Path(root).resolve(strict=True)
    current = root
    for part in parts:
        safe_segment(part)
        current = current / part
        if current.is_symlink():
            raise HTTPException(409, "Um atalho simbólico impede a recuperação.")
        # Existing intermediate directories must not be files.
    if not current.resolve(strict=False).is_relative_to(root):
        raise HTTPException(403, "Caminho fora da pasta autorizada.")
    return current


def remote_tree(db, account, root_id):
    """Reconstruct paths using only active catalog nodes of the same account."""
    root = db.execute(
        "SELECT id,kind FROM nodes WHERE id=? AND account=? AND trashed=0",
        (root_id, account),
    ).fetchone()
    if not root or root["kind"] != "folder":
        raise HTTPException(409, "Pasta remota não encontrada no catálogo.")
    rows = db.execute(
        "SELECT id,parent,name,kind,size,message_id,created FROM nodes "
        "WHERE account=? AND trashed=0", (account,),
    ).fetchall()
    if len(rows) > MAX_REMOTE_ITEMS:
        raise HTTPException(413, "Catálogo acima do limite da reconciliação.")
    children = {}
    for row in rows:
        children.setdefault(row["parent"], []).append(row)
    results = {}
    pending = [(root_id, (), set())]
    while pending:
        parent_id, prefix, ancestors = pending.pop()
        if parent_id in ancestors:
            raise HTTPException(422, "Ciclo no catálogo remoto.")
        visited = ancestors | {parent_id}
        for item in children.get(parent_id, []):
            segment = safe_segment(item["name"])
            parts = prefix + (segment,)
            if item["kind"] == "folder":
                pending.append((item["id"], parts, visited))
            elif item["kind"] == "file":
                if (not isinstance(item["message_id"], int) or item["message_id"] <= 0
                        or not isinstance(item["size"], int) or item["size"] < 0):
                    raise HTTPException(422, "Referência de arquivo remoto inválida.")
                rel = "/".join(parts)
                if rel not in results or (item["created"], item["id"]) > (results[rel]["created"], results[rel]["id"]):
                    results[rel] = dict(item)
            else:
                raise HTTPException(422, "Item remoto inválido.")
    return results


def conflict_name(path, node_id):
    path = Path(path)
    label = str(uuid.UUID(node_id)).split("-")[0]
    return path.with_name(f"{path.stem} (Telegram-{label}){path.suffix}")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            h.update(chunk)
    return h.digest()


def decision(local_path, node_id, known_node_id=None):
    """Specify the action without any destructive write.

    Any existing local file is treated as a potential conflict, until its
    bytes can be compared against the downloaded remote copy.
    """
    if not Path(local_path).exists() and not Path(local_path).is_symlink():
        return "download"
    if Path(local_path).is_dir() or Path(local_path).is_symlink():
        return "unsafe"
    if known_node_id == node_id:
        return "known"
    return "compare"


def install_download(downloaded_file, destination, root, node_id):
    """Copy bytes to a new path using O_EXCL, never truncating a local file.

    Returns a result and created path. If contents match, no write occurs.
    """
    destination = Path(destination)
    safe_relative(root, destination.relative_to(root).parts)
    if destination.exists():
        if destination.is_symlink() or not destination.is_file():
            raise HTTPException(409, "Conflito com arquivo ou atalho local.")
        if digest(destination) == digest(downloaded_file):
            return "identical", destination
        chosen = conflict_name(destination, node_id)
        if chosen.exists() or chosen.is_symlink():
            if chosen.is_file() and digest(chosen) == digest(downloaded_file):
                return "conflict_existing", chosen
            # Never replace a pre-existing conflict copy.
            chosen = chosen.with_name(chosen.stem + "-" + str(uuid.uuid4())[:8] + chosen.suffix)
    else:
        chosen = destination
    current = Path(root)
    for part in chosen.relative_to(root).parts[:-1]:
        current = current / safe_segment(part)
        if current.is_symlink():
            raise HTTPException(409, "Atalho simbólico encontrado no destino.")
        if not current.exists():
            current.mkdir(mode=0o700)
        if not current.is_dir():
            raise HTTPException(409, "Pasta de destino inválida.")
    fd = os.open(str(chosen), os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as output, Path(downloaded_file).open("rb") as source:
            shutil.copyfileobj(source, output, 1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
    except Exception:
        chosen.unlink(missing_ok=True)
        raise
    return ("conflict_saved" if chosen != destination else "downloaded"), chosen


async def get_remote_file(client, channel, item):
    """Restore both legacy and multipart files with integrity checking."""
    if item["size"] > MAX_FILE_BYTES:
        raise HTTPException(413, "Arquivo remoto acima do limite inicial de 20 GB.")
    with tempfile.NamedTemporaryFile(prefix=".dc-reconcile-", dir=str(DB_PATH.parent), delete=False) as temp:
        temp_path = Path(temp.name)
    os.chmod(temp_path, 0o600)
    try:
        await download_document(client, channel, item["message_id"], item["size"], temp_path)
        return temp_path
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
