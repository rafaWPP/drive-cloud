"""Local-only Telegram file catalog and small-file transfers.

The Telegram channel stores file bytes; SQLite stores the folder tree and
message references. Protect backend/.data as it contains sensitive sessions.
"""
import io
import hashlib
import os
import sqlite3
import time
import uuid
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
import pillow_jxl  # Register JPEG XL decoder for previews

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).resolve().parent / ".data" / "files.sqlite3"
MAX_SIZE = 20 * 1024 * 1024  # Initial bounded MVP, not a large-file backup tool.
Image.MAX_IMAGE_PIXELS = 35_000_000
THUMBS = DB_PATH.parent / "previews"
THUMBS.mkdir(parents=True, exist_ok=True)
def is_image(row):
    return row["mime"].startswith("image/") or row["name"].lower().endswith((".png",".jpg",".jpeg",".gif",".webp",".jxl",".bmp",".tif",".tiff"))
def prepare_image(raw, maximum):
    try:
        with Image.open(io.BytesIO(raw)) as source:
            frame = ImageOps.exif_transpose(source)
            frame.thumbnail((maximum, maximum), Image.Resampling.LANCZOS)
            if frame.mode not in ("RGB","L"):
                base=Image.new("RGB", frame.size, (30,30,30))
                if "A" in frame.getbands():
                    base.paste(frame, mask=frame.getchannel("A"))
                else:
                    base.paste(frame.convert("RGB"))
                frame=base
            out=io.BytesIO()
            frame.save(out, "JPEG", quality=84, optimize=True)
            return out.getvalue()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise HTTPException(415, "Não foi possível criar a prévia desta imagem.")


def connection():
    db = sqlite3.connect(str(DB_PATH), timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS nodes (
        id TEXT PRIMARY KEY, account TEXT NOT NULL, kind TEXT NOT NULL,
        parent TEXT, name TEXT NOT NULL, size INTEGER NOT NULL DEFAULT 0,
        mime TEXT NOT NULL DEFAULT 'application/octet-stream',
        message_id INTEGER, created INTEGER NOT NULL
    )""")
    cols = {r[1] for r in db.execute("PRAGMA table_info(nodes)")}
    if "trashed" not in cols:
        db.execute("ALTER TABLE nodes ADD COLUMN trashed INTEGER NOT NULL DEFAULT 0")
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

    @router.get("/preview/{file_id}")
    async def preview(file_id: str, full: bool = False):
        async with lock:
            client, account = await authorized_account()
            cid = channel_id(channel_links, account)
            with connection() as db:
                row = db.execute("SELECT * FROM nodes WHERE id=? AND account=? AND kind='file'",
                                 (file_id,account)).fetchone()
            if not row:
                raise HTTPException(404, "Arquivo não encontrado.")
            if not is_image(row):
                raise HTTPException(415, "A prévia é disponível apenas para imagens.")
            # Cache only derivatives, never unencrypted originals; directory is local and private.
            key = hashlib.sha256((account+":"+file_id+":"+str(row["message_id"])+":"+str(full)).encode()).hexdigest()
            target = THUMBS / (key+".jpg")
            if target.exists():
                return Response(target.read_bytes(), media_type="image/jpeg", headers={"Cache-Control":"private, max-age=120"})
            try:
                message = await client.get_messages(cid, ids=row["message_id"])
                if not message or not message.media:
                    raise HTTPException(404,"Imagem não encontrada no canal.")
                raw = await client.download_media(message, file=bytes)
                if not raw:
                    raise HTTPException(502,"Falha ao recuperar imagem.")
                image_bytes = prepare_image(raw, 1800 if full else 550)
                target.write_bytes(image_bytes)
                os.chmod(target, 0o600)
                return Response(image_bytes, media_type="image/jpeg", headers={"Cache-Control":"private, max-age=120"})
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(502, "Prévia indisponível: "+type(exc).__name__) from exc

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


    class ChangeInput(BaseModel):
        name: str | None = Field(default=None, max_length=180)
        parent: str | None = None
        trashed: bool | None = None

    @router.patch("/items/{item_id}")
    async def change_item(item_id: str, body: ChangeInput):
        async with lock:
            _, account = await authorized_account()
            channel_id(channel_links, account)
            with connection() as db:
                row = db.execute("SELECT * FROM nodes WHERE id=? AND account=?", (item_id, account)).fetchone()
                if not row:
                    raise HTTPException(404, "Item não encontrado.")
                if body.name is not None:
                    name = body.name.strip()
                    if not name or "/" in name or "\\\\" in name:
                        raise HTTPException(422, "Nome inválido.")
                    db.execute("UPDATE nodes SET name=? WHERE id=? AND account=?", (name, item_id, account))
                if "parent" in body.model_fields_set:
                    parent_valid(db, account, body.parent)
                    if body.parent == item_id:
                        raise HTTPException(409, "Uma pasta não pode ser movida para si mesma.")
                    cursor = body.parent
                    while cursor:
                        if cursor == item_id:
                            raise HTTPException(409, "Não é possível mover uma pasta para dentro dela mesma.")
                        ancestor = db.execute("SELECT parent FROM nodes WHERE id=? AND account=?", (cursor,account)).fetchone()
                        cursor = ancestor["parent"] if ancestor else None
                    db.execute("UPDATE nodes SET parent=? WHERE id=? AND account=?", (body.parent,item_id,account))
                if body.trashed is not None:
                    db.execute("UPDATE nodes SET trashed=? WHERE id=? AND account=?", (int(body.trashed),item_id,account))
            return {"ok": True}

    return router
