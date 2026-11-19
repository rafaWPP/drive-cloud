"""Local-only Telegram file catalog and small-file transfers.

The Telegram channel stores file bytes; SQLite stores the folder tree and
message references. Protect backend/.data as it contains sensitive sessions.
"""
import io
import os
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).resolve().parent / ".data" / "files.sqlite3"
MAX_SIZE = 20 * 1024 * 1024  # Initial bounded MVP, not a large-file backup tool.

def connection():
    db = sqlite3.connect(str(DB_PATH), timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS nodes (
        id TEXT PRIMARY KEY, account TEXT NOT NULL, kind TEXT NOT NULL,
        parent TEXT, name TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0,
        mime TEXT NOT NULL DEFAULT 'application/octet-stream',
        message_id INTEGER, created INTEGER NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS nodes_account_parent ON nodes(account,parent)")
    return db

def channel_id(links, user_id):
    entry = links().get(user_id)
    if not entry:
        raise HTTPException(409, "Configure o canal privado em Conexão Telegram primeiro.")
    return int(entry["channel_id"])

def parent_valid(db, account, parent):
    if not parent:
        return
    row = db.execute("SELECT kind FROM nodes WHERE id=? AND account=?", (parent, account)).fetchone()
    if not row or row["kind"] != "folder":
        raise HTTPException(404, "Pasta de destino não encontrada.")

def as_item(row):
    return dict(row)

class FolderInput(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    parent: str | None = None

def build_router(authorized_account, channel_links, lock):
    router = APIRouter(prefix="/api/cloud")

    @router.get("/items")
    async def items():
        async with lock:
            _, account = await authorized_account()
            channel_id(channel_links, account)
            with connection() as db:
                rows = db.execute("SELECT * FROM nodes WHERE account=? ORDER BY kind DESC, name COLLATE NOCASE",
                                  (account,)).fetchall()
                return {"items": [as_item(r) for r in rows], "max_upload_bytes": MAX_SIZE}

    @router.post("/folders")
    async def create_folder(body: FolderInput):
        async with lock:
            _, account = await authorized_account()
            channel_id(channel_links, account)
            name = body.name.strip()
            if not name or '/' in name or '\\' in name:
                raise HTTPException(422, "Nome de pasta inválido.")
            with connection() as db:
                parent_valid(db, account, body.parent)
                id_ = str(uuid.uuid4())
                db.execute("INSERT INTO nodes (id,account,kind,parent,name,created) VALUES (?,?,?,?,?,?)",
                           (id_,account,"folder",body.parent,name,int(time.time()*1000)))
            return {"id": id_, "kind": "folder", "name": name}

    @router.post("/upload")
    async def upload(file: UploadFile = File(...), parent: str | None = Form(None)):
        # This pilot limits files to 20 MiB. Use chunked transfers in a later version.
        async with lock:
            client, account = await authorized_account()
            cid = channel_id(channel_links, account)
            with connection() as db:
                parent_valid(db, account, parent)
            name = os.path.basename((file.filename or "arquivo").replace("\\", "/"))[:180]
            if name in (".", "..", ""):
                raise HTTPException(422, "Nome inválido.")
            data = await file.read(MAX_SIZE + 1)
            if len(data) > MAX_SIZE:
                raise HTTPException(413, "Limite desta versão: 20 MB por arquivo.")
            buffer = io.BytesIO(data)
            buffer.name = name
            try:
                msg = await client.send_file(cid, buffer, force_document=True, caption="Drive Cloud • arquivo", part_size_kb=512)
            except Exception as exc:
                raise HTTPException(502, "Falha ao enviar ao Telegram: " + type(exc).__name__) from exc
            id_ = str(uuid.uuid4())
            try:
                with connection() as db:
                    db.execute("""INSERT INTO nodes
                               (id,account,kind,parent,name,size,mime,message_id,created)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                               (id_,account,"file",parent,name,len(data),
                                file.content_type or "application/octet-stream",msg.id,int(time.time()*1000)))
            except Exception as exc:
                # The message may exist on Telegram even if catalog persistence fails.
                raise HTTPException(500, "Arquivo enviado, mas catálogo local não foi gravado. Não reenvie antes de conferir o canal.") from exc
            return {"id": id_, "kind": "file", "name": name, "size": len(data)}

    @router.get("/download/{file_id}")
    async def download(file_id: str):
        async with lock:
            client, account = await authorized_account()
            cid = channel_id(channel_links, account)
            with connection() as db:
                row = db.execute("SELECT * FROM nodes WHERE id=? AND account=? AND kind='file'",
                                 (file_id,account)).fetchone()
            if not row:
                raise HTTPException(404, "Arquivo não encontrado.")
            try:
                msg = await client.get_messages(cid, ids=row["message_id"])
                if not msg or not msg.media:
                    raise HTTPException(404, "Arquivo não encontrado no canal do Telegram.")
                raw = await client.download_media(msg, file=bytes)
                if raw is None:
                    raise HTTPException(502, "Não foi possível recuperar arquivo.")
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(502, "Falha no download do Telegram: " + type(exc).__name__) from exc
            # Frontend uses Blob download attribute; no untrusted filenames in headers.
            return Response(content=raw, media_type="application/octet-stream",
                            headers={"Cache-Control":"no-store"})

    return router
