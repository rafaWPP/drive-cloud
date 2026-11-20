"""Crash-resilient local upload staging for Drive Cloud.

This resumes browser -> local backend transfer at a verified byte offset.
It does NOT resume Telegram's own upload mid-file. Sending uncertainty fails
closed to avoid silently creating duplicate Telegram messages.
"""
import hashlib
import os
import re
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from telethon.tl.types import DocumentAttributeFilename

from storage_api import DB_PATH, MAX_SIZE, connection, parent_valid, channel_id, update_upload_progress

CHUNK_SIZE = 1024 * 1024
MAX_STAGED_BYTES = 4 * MAX_SIZE
MAX_ACTIVE_SESSIONS = 16
STAGE_DIR = DB_PATH.parent / "resumable_staging"
STAGE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
try:
    STAGE_DIR.chmod(0o700)
except OSError:
    pass


class StartBody(BaseModel):
    upload_id: uuid.UUID
    name: str = Field(min_length=1, max_length=180)
    size: int = Field(ge=1, le=MAX_SIZE)
    mime: str = Field(default="application/octet-stream", max_length=160)
    signature: str = Field(pattern=r"^[a-f0-9]{64}$")
    parent: uuid.UUID | None = None


def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS resumable_uploads (
        id TEXT PRIMARY KEY, account TEXT NOT NULL, channel TEXT NOT NULL,
        parent TEXT, name TEXT NOT NULL, size INTEGER NOT NULL,
        mime TEXT NOT NULL, signature TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'staging',
        message_id INTEGER, node_id TEXT, updated INTEGER NOT NULL)""")
    db.execute("CREATE INDEX IF NOT EXISTS resumable_account ON resumable_uploads(account,state,updated)")


def stage_path(upload_id):
    return STAGE_DIR / (str(uuid.UUID(str(upload_id))) + ".part")


def check_name(name):
    if (name in (".", "..") or name.strip() != name or
            any(ch in name for ch in "/\\\x00") or
            any(ord(ch) < 32 for ch in name) or
            len(name) > 180):
        raise HTTPException(422, "Nome de arquivo inválido.")
    return name


def file_size(path):
    if path.is_symlink():
        raise HTTPException(409, "Arquivo temporário inválido.")
    try:
        return path.stat().st_size
    except OSError as exc:
        raise HTTPException(409, "Parte local indisponível; preserve os arquivos e inicie outro upload.") from exc


def apply_chunk(path, offset, expected, content, checksum):
    """Idempotent, fsync'd append with strong per-chunk integrity checking."""
    if not 0 < len(content) <= CHUNK_SIZE:
        raise HTTPException(413, "Cada parte deve ter no máximo 1 MB.")
    if not re.fullmatch(r"[a-f0-9]{64}", checksum or ""):
        raise HTTPException(422, "Hash de parte inválido.")
    if hashlib.sha256(content).hexdigest() != checksum:
        raise HTTPException(422, "Parte corrompida; reenviar sem avançar.")
    current = file_size(path)
    if offset < 0 or offset + len(content) > expected:
        raise HTTPException(416, "Intervalo fora dos limites do arquivo.")
    if offset < current:
        if offset + len(content) <= current:
            with path.open("rb") as file:
                file.seek(offset)
                if file.read(len(content)) == content:
                    return current
        raise HTTPException(409, "Posição desatualizada; consulte o upload e continue do offset correto.")
    if offset != current:
        raise HTTPException(409, "Parte fora de ordem; consulte a posição atual.")
    with path.open("ab") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())
    return file_size(path)


def row_status(row, offset):
    return {"upload_id": row["id"], "state": row["state"], "offset": offset,
            "size": row["size"], "max_chunk_size": CHUNK_SIZE,
            "completed": row["state"] == "completed",
            "node_id": row["node_id"] if row["state"] == "completed" else None}


def get_session(db, upload_id, account, channel):
    row = db.execute("SELECT * FROM resumable_uploads WHERE id=? AND account=? AND channel=?",
                     (str(upload_id), account, str(channel))).fetchone()
    if not row:
        raise HTTPException(404, "Envio não encontrado para esta conta e canal.")
    return row


def caption(upload_id):
    return "Drive Cloud • upload-id:" + str(upload_id)


def build_resumable_router(authorized_account, channel_links, lock):
    router = APIRouter(prefix="/api/cloud/resumable")

    @router.post("/start")
    async def start(body: StartBody):
        check_name(body.name)
        upload_id = str(body.upload_id)
        async with lock:
            _, account = await authorized_account()
            channel = channel_id(channel_links, account)
            with connection() as db:
                schema(db)
                parent = str(body.parent) if body.parent is not None else None
                parent_valid(db, account, parent)
                existing = db.execute("SELECT * FROM resumable_uploads WHERE id=?", (upload_id,)).fetchone()
                if existing:
                    if (existing["account"] != account or existing["channel"] != str(channel) or
                            existing["parent"] != parent or existing["name"] != body.name or
                            existing["size"] != body.size or existing["signature"] != body.signature or
                            existing["mime"] != body.mime):
                        raise HTTPException(409, "Este ID de upload pertence a outro arquivo, pasta ou conta.")
                    return row_status(existing, 0 if existing["state"] == "completed" else file_size(stage_path(upload_id)))
                active = db.execute("SELECT id,size FROM resumable_uploads WHERE state != 'completed'").fetchall()
                if len(active) >= MAX_ACTIVE_SESSIONS or sum(int(x["size"]) for x in active) + body.size > MAX_STAGED_BYTES:
                    raise HTTPException(429, "Muitos uploads pendentes. Conclua ou cancele os anteriores.")
                path = stage_path(upload_id)
                if path.exists() or path.is_symlink():
                    raise HTTPException(409, "Já existe um arquivo temporário com este identificador.")
                with path.open("xb") as output:
                    os.chmod(path, 0o600)
                    output.flush()
                    os.fsync(output.fileno())
                try:
                    db.execute(
                        "INSERT INTO resumable_uploads "
                        "(id,account,channel,parent,name,size,mime,signature,updated) VALUES (?,?,?,?,?,?,?,?,?)",
                        (upload_id, account, str(channel), parent, body.name, body.size, body.mime,
                         body.signature, int(time.time())),
                    )
                except sqlite3.Error:
                    path.unlink(missing_ok=True)
                    raise
                row = get_session(db, upload_id, account, channel)
            return row_status(row, 0)

    @router.get("/{upload_id}")
    async def status(upload_id: uuid.UUID):
        async with lock:
            _, account = await authorized_account()
            channel = channel_id(channel_links, account)
            with connection() as db:
                schema(db)
                row = get_session(db, upload_id, account, channel)
                return row_status(row, 0 if row["state"] == "completed" else file_size(stage_path(upload_id)))

    @router.put("/{upload_id}/chunk")
    async def put_chunk(upload_id: uuid.UUID, request: Request,
                        offset: int = Query(ge=0),
                        checksum: str = Query(min_length=64, max_length=64)):
        # Bound memory usage even if a client sends a maliciously large payload.
        parts = bytearray()
        async for segment in request.stream():
            if len(parts) + len(segment) > CHUNK_SIZE:
                raise HTTPException(413, "Parte superior ao limite de 1 MB.")
            parts.extend(segment)
        async with lock:
            _, account = await authorized_account()
            channel = channel_id(channel_links, account)
            with connection() as db:
                schema(db)
                row = get_session(db, upload_id, account, channel)
                if row["state"] != "staging":
                    raise HTTPException(409, "Este envio não aceita novas partes.")
                pos = apply_chunk(stage_path(upload_id), offset, row["size"], bytes(parts), checksum)
                db.execute("UPDATE resumable_uploads SET updated=? WHERE id=?",
                           (int(time.time()), str(upload_id)))
            return {"offset": pos, "size": row["size"]}

    async def find_sent(client, channel, upload_id):
        marker = caption(upload_id)
        async for message in client.iter_messages(channel, search=marker, limit=30):
            if message.message == marker and message.file:
                return message
        return None

    async def persist_sent(db, row, account, msg_id):
        node_id = row["node_id"] or str(uuid.uuid4())
        previous = db.execute("SELECT id FROM nodes WHERE id=? AND account=?", (node_id, account)).fetchone()
        if not previous:
            parent_valid(db, account, row["parent"])
            db.execute(
                "INSERT INTO nodes (id,account,kind,parent,name,size,mime,message_id,created) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (node_id, account, "file", row["parent"], row["name"], row["size"], row["mime"],
                 msg_id, int(time.time()*1000)),
            )
        db.execute("UPDATE resumable_uploads SET state='completed',message_id=?,node_id=?,updated=? WHERE id=?",
                   (msg_id, node_id, int(time.time()), row["id"]))
        return node_id

    @router.post("/{upload_id}/complete")
    async def complete(upload_id: uuid.UUID):
        async with lock:
            client, account = await authorized_account()
            channel = channel_id(channel_links, account)
            with connection() as db:
                schema(db)
                row = get_session(db, upload_id, account, channel)
                if row["state"] == "completed":
                    return {"completed": True, "node_id": row["node_id"], "recovered": False}
                if file_size(stage_path(upload_id)) != row["size"]:
                    raise HTTPException(409, "Arquivo ainda incompleto. Retome as partes pendentes.")
                first_call = row["state"] == "staging"
                if first_call:
                    db.execute("UPDATE resumable_uploads SET state='sending',updated=? WHERE id=?",
                               (int(time.time()), str(upload_id)))
                elif row["state"] not in ("sending", "sent"):
                    raise HTTPException(409, "Estado do upload inválido.")
            # Prefer the exact Telegram message ID when sending succeeded but
            # the local catalog commit failed; search is a fallback for a lost ACK.
            message = None
            if row["message_id"]:
                try:
                    known = await client.get_messages(channel, ids=row["message_id"])
                    if known and known.message == caption(upload_id) and known.file:
                        message = known
                except Exception:
                    pass
            if message is None:
                message = await find_sent(client, channel, upload_id)
            if message is None:
                if not first_call:
                    raise HTTPException(409, "Envio anterior incerto. Confira o canal do Telegram antes de tentar outro.")
            else:
                with connection() as db:
                    schema(db)
                    row = get_session(db, upload_id, account, channel)
                    node = await persist_sent(db, row, account, message.id)
                stage_path(upload_id).unlink(missing_ok=True)
                update_upload_progress(str(upload_id), "completed", row["size"], row["size"])
                return {"completed": True, "node_id": node, "recovered": True}
            update_upload_progress(str(upload_id), "telegram", 0, row["size"])
            try:
                def on_progress(sent, total):
                    update_upload_progress(str(upload_id), "telegram", sent, total)
                message = await client.send_file(
                    channel, str(stage_path(upload_id)), force_document=True,
                    caption=caption(upload_id), part_size_kb=512,
                    mime_type=row["mime"],
                    attributes=[DocumentAttributeFilename(row["name"])],
                    progress_callback=on_progress,
                )
            except Exception as exc:
                update_upload_progress(str(upload_id), "uncertain")
                # Never mark this session ready to retry until its Telegram state is known.
                raise HTTPException(502, "Envio ao Telegram não confirmado. Verifique o canal antes de reenviar.") from exc
            with connection() as db:
                schema(db)
                row = get_session(db, upload_id, account, channel)
                db.execute("UPDATE resumable_uploads SET state='sent',message_id=?,updated=? WHERE id=?",
                           (message.id, int(time.time()), str(upload_id)))
                node = await persist_sent(db, row, account, message.id)
            stage_path(upload_id).unlink(missing_ok=True)
            update_upload_progress(str(upload_id), "completed", row["size"], row["size"])
            return {"completed": True, "node_id": node, "recovered": False}

    @router.delete("/{upload_id}")
    async def cancel(upload_id: uuid.UUID):
        async with lock:
            _, account = await authorized_account()
            channel = channel_id(channel_links, account)
            with connection() as db:
                schema(db)
                row = get_session(db, upload_id, account, channel)
                if row["state"] != "staging":
                    raise HTTPException(409, "Não é seguro cancelar um envio já encaminhado ao Telegram.")
                db.execute("DELETE FROM resumable_uploads WHERE id=?", (str(upload_id),))
            stage_path(upload_id).unlink(missing_ok=True)
            return {"cancelled": True}

    return router
