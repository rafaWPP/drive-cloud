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
import asyncio
import zipfile
import tempfile
from pathlib import Path
from PIL import Image, ImageOps, UnidentifiedImageError
import pillow_jxl  # Register JPEG XL decoder for previews

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import Response, FileResponse
from starlette.background import BackgroundTask
from pydantic import BaseModel, Field

DB_PATH = (Path(os.environ["DRIVE_CLOUD_DATA_DIR"]).expanduser() if os.environ.get("DRIVE_CLOUD_DATA_DIR") else Path(__file__).resolve().parent / ".data") / "files.sqlite3"
MAX_SIZE = 512 * 1024 * 1024  # Bounded 512 MiB per file; Telegram handles 512 KiB transfer parts.
MAX_PREVIEW_SIZE = 20 * 1024 * 1024  # RAM-backed previews remain deliberately small.
# Transient progress is local to the running backend process.
UPLOAD_PROGRESS = {}
ZIP_JOBS = {}
ZIP_MAX_ITEMS = 250
ZIP_MAX_TOTAL = 300 * 1024 * 1024
ZIP_DIR = DB_PATH.parent / 'zip_exports'
ZIP_DIR.mkdir(parents=True,exist_ok=True)

def update_upload_progress(upload_id, stage, sent=0, total=0):
    if not upload_id:
        return
    UPLOAD_PROGRESS[upload_id] = {"stage": stage, "sent": int(sent),
                                   "total": int(total), "updated": time.monotonic()}
    if len(UPLOAD_PROGRESS) > 256:
        oldest = sorted(UPLOAD_PROGRESS, key=lambda k: UPLOAD_PROGRESS[k]["updated"])
        for key in oldest[:64]:
            UPLOAD_PROGRESS.pop(key, None)

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
    if "starred" not in cols:
        db.execute("ALTER TABLE nodes ADD COLUMN starred INTEGER NOT NULL DEFAULT 0")
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

    @router.get("/upload-progress/{upload_id}")
    async def upload_progress(upload_id: str):
        try:
            uuid.UUID(upload_id)
        except ValueError:
            raise HTTPException(422, "Identificador inválido.")
        status = UPLOAD_PROGRESS.get(upload_id)
        if not status:
            return {"stage": "pending", "sent": 0, "total": 0}
        return {k:v for k,v in status.items() if k != "updated"}

    @router.post("/upload")
    async def upload(file: UploadFile = File(...), parent: str | None = Form(None),
                     upload_id: str | None = Form(None)):
        if upload_id is not None:
            try:
                uuid.UUID(upload_id)
            except ValueError:
                raise HTTPException(422, "Identificador de upload inválido.")
        # This pilot limits files to 20 MiB. Use chunked transfers in a later version.
        async with lock:
            client, account = await authorized_account()
            cid = channel_id(channel_links, account)
            with connection() as db:
                parent_valid(db, account, parent)
            name = os.path.basename((file.filename or "arquivo").replace("\\", "/"))[:180]
            if name in (".", "..", ""):
                raise HTTPException(422, "Nome inválido.")
            if chr(0) in name:
                raise HTTPException(422, "Nome de arquivo inválido.")
            # Never hold the whole upload in RAM. A private temporary file is
            # removed even when Telegram rejects the transfer.
            with tempfile.TemporaryDirectory(prefix=".dc-upload-", dir=str(DB_PATH.parent)) as folder:
                target = Path(folder) / name
                total_bytes = 0
                with target.open("xb") as output:
                    os.chmod(target, 0o600)
                    while True:
                        chunk = await file.read(min(1024 * 1024, MAX_SIZE - total_bytes + 1))
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > MAX_SIZE:
                            raise HTTPException(413, "Limite atual: 512 MB por arquivo.")
                        output.write(chunk)
                update_upload_progress(upload_id, "telegram", 0, total_bytes)
                def report_progress(sent, total):
                    update_upload_progress(upload_id, "telegram", sent, total)
                try:
                    msg = await client.send_file(
                        cid, str(target), force_document=True,
                        caption="Drive Cloud • arquivo", part_size_kb=512,
                        progress_callback=report_progress
                    )
                    update_upload_progress(upload_id, "catalog", total_bytes, total_bytes)
                except Exception as exc:
                    update_upload_progress(upload_id, "failed")
                    raise HTTPException(502, "Falha ao enviar ao Telegram: " + type(exc).__name__) from exc
            id_ = str(uuid.uuid4())
            try:
                with connection() as db:
                    db.execute("""INSERT INTO nodes
                               (id,account,kind,parent,name,size,mime,message_id,created)
                               VALUES (?,?,?,?,?,?,?,?,?)""",
                               (id_,account,"file",parent,name,total_bytes,
                                file.content_type or "application/octet-stream",msg.id,int(time.time()*1000)))
            except Exception as exc:
                # The message may exist on Telegram even if catalog persistence fails.
                raise HTTPException(500, "Arquivo enviado, mas catálogo local não foi gravado. Não reenvie antes de conferir o canal.") from exc
            update_upload_progress(upload_id, "completed", total_bytes, total_bytes)
            return {"id": id_, "kind": "file", "name": name, "size": total_bytes}

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
            if int(row["size"]) > MAX_PREVIEW_SIZE:
                raise HTTPException(413, "Arquivo acima do limite de prévia. Faça o download para visualizar.")
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

    def zip_safe_name(value: str) -> str:
        clean = str(value or "arquivo").replace("\\", "_").replace("/", "_").replace(chr(0), "_").strip()
        return clean if clean not in ("", ".", "..") else "arquivo"

    @router.post("/folders/{folder_id}/zip")
    async def prepare_folder_zip(folder_id: str):
        """Create a temporary ZIP containing the selected folder's hierarchy."""
        async with lock:
            client, account = await authorized_account()
            cid = channel_id(channel_links, account)
            with connection() as db:
                all_rows = [dict(row) for row in db.execute(
                    "SELECT * FROM nodes WHERE account=? AND trashed=0", (account,)).fetchall()]
            mapping = {row["id"]:row for row in all_rows}
            root = mapping.get(folder_id)
            if not root or root["kind"] != "folder":
                raise HTTPException(404, "Pasta não encontrada.")
            children = {}
            for row in all_rows:
                children.setdefault(row["parent"], []).append(row)
            entries = []
            todo = [(root, zip_safe_name(root["name"]) + "/")]
            visited = set()
            while todo:
                row, path = todo.pop()
                if row["id"] in visited:
                    raise HTTPException(409,"Hierarquia de pastas inválida.")
                visited.add(row["id"])
                entries.append((row,path))
                if len(entries) > ZIP_MAX_ITEMS:
                    raise HTTPException(413,"Máximo de 250 itens por ZIP nesta versão.")
                if row["kind"]=="folder":
                    for child in children.get(row["id"],[]):
                        filename=zip_safe_name(child["name"])
                        todo.append((child,path+filename+("/" if child["kind"]=="folder" else "")))
            total = sum(int(row["size"]) for row,_ in entries if row["kind"]=="file")
            if total > ZIP_MAX_TOTAL:
                raise HTTPException(413,"Limite de 300 MB de arquivos por ZIP nesta versão.")
            if len([j for j in ZIP_JOBS.values() if j["state"] in ("preparing","downloading")]) >= 2:
                raise HTTPException(429,"Já existem duas compactações em andamento.")
            now = time.monotonic()
            for key,job in list(ZIP_JOBS.items()):
                if now-job["updated"] > 1800 and job["state"] not in ("preparing","downloading"):
                    if job.get("path"):
                        Path(job["path"]).unlink(missing_ok=True)
                    ZIP_JOBS.pop(key,None)
            task_id = str(uuid.uuid4())
            target = ZIP_DIR / (task_id+".zip")
            ZIP_JOBS[task_id] = {"owner":account,"state":"preparing","done":0,
                "count":len(entries),"total_bytes":total,"processed_bytes":0,
                "name":zip_safe_name(root["name"])+".zip","path":str(target), "phase":"waiting",
                "updated":time.monotonic(),"error":None}
            async def build():
                job = ZIP_JOBS[task_id]
                job["state"]="downloading"
                job["phase"]="telegram"
                used_names=set()
                try:
                    with zipfile.ZipFile(target,"w",compression=zipfile.ZIP_DEFLATED,
                                         compresslevel=5,allowZip64=True) as archive:
                        for row,arcname in entries:
                            # Prevent duplicate ZIP entries when siblings have the same name.
                            if arcname in used_names:
                                raise RuntimeError("Nomes duplicados na mesma pasta. Renomeie os itens antes de compactar.")
                            used_names.add(arcname)
                            if row["kind"]=="folder":
                                archive.writestr(arcname,b"")
                            else:
                                message=await client.get_messages(cid,ids=row["message_id"])
                                if not message or not message.media:
                                    raise RuntimeError("Arquivo ausente no canal: "+row["name"])
                                baseline = job["processed_bytes"]
                                def zip_download_progress(received, total):
                                    job["processed_bytes"] = min(ZIP_MAX_TOTAL, baseline+max(0,int(received)))
                                    job["updated"] = time.monotonic()
                                raw=await client.download_media(message,file=bytes,progress_callback=zip_download_progress)
                                if raw is not None and baseline+len(raw)>ZIP_MAX_TOTAL:
                                    raise RuntimeError("O tamanho real dos arquivos ultrapassa 300 MB.")
                                if raw is None:
                                    raise RuntimeError("Falha ao recuperar: "+row["name"])
                                job["phase"]="compressing"
                                await asyncio.to_thread(archive.writestr,arcname,raw)
                                job["processed_bytes"]=baseline+len(raw)
                                job["phase"]="telegram"
                            job["done"]+=1
                            job["updated"]=time.monotonic()
                            await asyncio.sleep(0)
                    os.chmod(target,0o600)
                    job["state"]="ready"
                    job["phase"]="ready"
                except Exception as exc:
                    target.unlink(missing_ok=True)
                    job["state"]="failed"
                    job["phase"]="failed"
                    job["error"]=str(exc)[:200]
                finally:
                    job["updated"]=time.monotonic()
            asyncio.create_task(build())
            return {"job_id":task_id,"count":len(entries),"total_bytes":total}

    @router.get("/zip/{job_id}")
    async def folder_zip_status(job_id: str):
        try:
            uuid.UUID(job_id)
        except ValueError:
            raise HTTPException(422,"Identificador inválido.")
        _, account = await authorized_account()
        job=ZIP_JOBS.get(job_id)
        if not job or job["owner"]!=account:
            raise HTTPException(404,"Compactação não encontrada.")
        return {key:job[key] for key in ("state","done","count","total_bytes","processed_bytes","phase","error","name")}

    @router.get("/zip/{job_id}/download")
    async def download_folder_zip(job_id: str):
        try:
            uuid.UUID(job_id)
        except ValueError:
            raise HTTPException(422,"Identificador inválido.")
        _, account = await authorized_account()
        job=ZIP_JOBS.get(job_id)
        if not job or job["owner"]!=account:
            raise HTTPException(404,"Compactação não encontrada.")
        if job["state"]!="ready" or not Path(job["path"]).exists():
            raise HTTPException(409,"O arquivo ZIP ainda não está pronto.")
        return FileResponse(job["path"],media_type="application/zip",filename=job["name"],
                            headers={"Cache-Control":"no-store"},
                            background=BackgroundTask(lambda: Path(job["path"]).unlink(missing_ok=True)))

    @router.get("/media-status/{file_id}")
    async def video_preview_status(file_id: str):
        try:
            uuid.UUID(file_id)
        except (ValueError, TypeError):
            raise HTTPException(422, "Identificador inválido.")
        async with lock:
            client, account = await authorized_account()
            cid = channel_id(channel_links, account)
            with connection() as db:
                row = db.execute(
                    "SELECT * FROM nodes WHERE id=? AND account=? AND kind='file' AND trashed=0",
                    (file_id, account)
                ).fetchone()
            if not row:
                raise HTTPException(404, "Vídeo não encontrado no catálogo.")
            if not row["name"].lower().endswith((".mp4", ".m4v", ".webm")):
                raise HTTPException(415, "Este formato não tem prévia de vídeo.")
            if int(row["size"]) > MAX_PREVIEW_SIZE:
                raise HTTPException(413, "Vídeo acima do limite de prévia local.")
            msg = await client.get_messages(cid, ids=row["message_id"])
            if not msg or not msg.media:
                raise HTTPException(404, "Vídeo não encontrado no Telegram.")
        return {"ready": True, "name": row["name"]}

    @router.get("/media/{file_id}")
    async def stream_video_preview(file_id: str, request: Request):
        """Authenticated local preview with byte ranges; never an attachment download."""
        import re
        try:
            uuid.UUID(file_id)
        except (ValueError, TypeError):
            raise HTTPException(422, "Identificador inválido.")
        async with lock:
            client, account = await authorized_account()
            cid = channel_id(channel_links, account)
            with connection() as db:
                item = db.execute(
                    "SELECT * FROM nodes WHERE id=? AND account=? AND kind='file' AND trashed=0",
                    (file_id, account)
                ).fetchone()
            if not item:
                raise HTTPException(404, "Vídeo não encontrado.")
            extension = item["name"].lower().rsplit(".", 1)[-1]
            video_types = {"mp4": "video/mp4", "webm": "video/webm", "m4v": "video/mp4"}
            mime = video_types.get(extension)
            if mime is None:
                raise HTTPException(415, "Formato de vídeo não suportado na prévia.")
            if int(item["size"]) > MAX_PREVIEW_SIZE:
                raise HTTPException(413, "Vídeo ultrapassa o limite de prévia local.")
            # The RAM cache also serves media in scoped sharing pages.
            from share_api import cached_media_get, cached_media_put
            cache_key = (account, cid, item["message_id"], str(item["id"]))
            data = cached_media_get(cache_key)
            if data is None:
                msg = await client.get_messages(cid, ids=item["message_id"])
                if not msg or not msg.media:
                    raise HTTPException(404, "Vídeo ausente no canal Telegram.")
                data = await client.download_media(msg, file=bytes)
                if data is None:
                    raise HTTPException(502, "Não foi possível recuperar o vídeo.")
                if len(data) > MAX_PREVIEW_SIZE:
                    raise HTTPException(413, "Prévia local maior que o limite permitido.")
                cached_media_put(cache_key, data)
        total = len(data)
        headers = {"Cache-Control":"private, no-store",
                   "X-Content-Type-Options":"nosniff",
                   "Accept-Ranges":"bytes"}
        byte_range = request.headers.get("range")
        if byte_range:
            match = re.fullmatch(r"bytes=(\d*)-(\d*)", byte_range.strip())
            if not match or not any(match.groups()):
                raise HTTPException(416, "Intervalo inválido.", headers={"Content-Range":f"bytes */{total}"})
            if match.group(1):
                start = int(match.group(1))
                end = int(match.group(2)) if match.group(2) else total - 1
            else:
                suffix = int(match.group(2))
                start, end = max(0, total - suffix), total - 1
            if total == 0 or start >= total or end < start or end >= total:
                raise HTTPException(416, "Intervalo fora do vídeo.", headers={"Content-Range":f"bytes */{total}"})
            headers["Content-Range"] = f"bytes {start}-{end}/{total}"
            return Response(data[start:end + 1], status_code=206, media_type=mime, headers=headers)
        return Response(data, media_type=mime, headers=headers)

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
                # Download into a private file instead of allocating hundreds
                # of megabytes of Python RAM, then stream it to the UI.
                with tempfile.NamedTemporaryFile(prefix=".dc-download-", dir=str(DB_PATH.parent),
                                                 delete=False) as temporary:
                    temporary_path = Path(temporary.name)
                os.chmod(temporary_path, 0o600)
                try:
                    saved = await client.download_media(msg, file=str(temporary_path))
                    if not saved or not temporary_path.exists():
                        raise HTTPException(502, "Não foi possível recuperar arquivo.")
                except Exception:
                    temporary_path.unlink(missing_ok=True)
                    raise
            except HTTPException:
                raise
            except Exception as exc:
                raise HTTPException(502, "Falha no download do Telegram: " + type(exc).__name__) from exc
            return FileResponse(
                temporary_path, media_type="application/octet-stream",
                headers={"Cache-Control": "no-store"},
                background=BackgroundTask(lambda: temporary_path.unlink(missing_ok=True)),
            )


    class ChangeInput(BaseModel):
        name: str | None = Field(default=None, max_length=180)
        parent: str | None = None
        trashed: bool | None = None
        starred: bool | None = None

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
                if body.starred is not None:
                    db.execute("UPDATE nodes SET starred=? WHERE id=? AND account=?", (int(body.starred),item_id,account))
            return {"ok": True}


    @router.get("/usage")
    async def usage():
        """Catalog totals for this account, not Telegram account quota."""
        async with lock:
            _, account = await authorized_account()
            channel_id(channel_links, account)
            with connection() as db:
                stats = db.execute("""SELECT
                    COUNT(*) AS total_items,
                    COALESCE(SUM(CASE WHEN kind='file' THEN size ELSE 0 END),0) AS total_bytes,
                    COALESCE(SUM(CASE WHEN kind='file' AND trashed=0 THEN size ELSE 0 END),0) AS active_bytes,
                    COALESCE(SUM(CASE WHEN kind='file' AND trashed=1 THEN size ELSE 0 END),0) AS trash_bytes,
                    SUM(CASE WHEN kind='file' THEN 1 ELSE 0 END) AS files
                    FROM nodes WHERE account=?""", (account,)).fetchone()
            return {**dict(stats), "scope": "drive_catalog", "quota_bytes": None}

    @router.get("/catalog/export")
    async def export_catalog():
        """Portable metadata snapshot; does not contain Telegram credentials or file bytes."""
        import json
        from datetime import datetime, timezone
        async with lock:
            _, account = await authorized_account()
            cid = channel_id(channel_links, account)
            with connection() as db:
                rows = db.execute("SELECT id,kind,parent,name,size,mime,message_id,created,trashed,starred FROM nodes WHERE account=? ORDER BY created,id",(account,)).fetchall()
            payload = {"format":"drive-cloud-catalog","version":1,
                       "exported_at":datetime.now(timezone.utc).isoformat(),
                       "telegram_account":account,"channel_id":str(cid),
                       "items":[dict(r) for r in rows]}
            result = json.dumps(payload,ensure_ascii=False,indent=2).encode("utf-8")
            return Response(content=result,media_type="application/json",
                            headers={"Content-Disposition":'attachment; filename="drive-cloud-catalog.json"',
                                     "Cache-Control":"no-store"})

    @router.post("/catalog/import")
    async def import_catalog(file: UploadFile = File(...), dry_run: bool = Form(True)):
        """Validate a same-account/channel catalog export; add missing metadata only."""
        import json
        limit = 2 * 1024 * 1024
        raw = await file.read(limit + 1)
        if len(raw) > limit:
            raise HTTPException(413, "O catálogo deve ter no máximo 2 MB.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise HTTPException(422, "O arquivo não contém JSON válido.") from exc
        if not isinstance(payload, dict) or payload.get("format") != "drive-cloud-catalog" or payload.get("version") != 1:
            raise HTTPException(422, "Formato de catálogo incompatível.")
        entries = payload.get("items")
        if not isinstance(entries, list) or len(entries) > 10000:
            raise HTTPException(422, "Lista inválida ou acima de 10 mil itens.")

        async with lock:
            _, account = await authorized_account()
            cid = channel_id(channel_links, account)
            if payload.get("telegram_account") != account or str(payload.get("channel_id")) != str(cid):
                raise HTTPException(409, "Este catálogo pertence a outra conta ou canal Telegram.")

            valid = []
            seen = set()
            for data in entries:
                if not isinstance(data, dict):
                    raise HTTPException(422, "Item inválido no catálogo.")
                try:
                    item_id = str(uuid.UUID(data["id"]))
                    kind = data["kind"]
                    parent = data.get("parent")
                    parent = str(uuid.UUID(parent)) if parent is not None else None
                    name = data["name"]
                    size = data["size"]
                    mime = data["mime"]
                    msg = data.get("message_id")
                    created = data["created"]
                    trashed = data.get("trashed", 0)
                    starred = data.get("starred", 0)
                except (KeyError, ValueError, TypeError, AttributeError) as exc:
                    raise HTTPException(422, "Metadados inválidos no catálogo.") from exc
                if (item_id in seen or kind not in ("file", "folder") or
                    not isinstance(name, str) or not name.strip() or len(name) > 180 or
                    not isinstance(size, int) or isinstance(size, bool) or size < 0 or
                    not isinstance(mime, str) or len(mime) > 160 or
                    not isinstance(created, int) or isinstance(created, bool) or created < 0 or
                    trashed not in (0, 1, False, True) or starred not in (0, 1, False, True) or
                    (kind == "file" and (not isinstance(msg, int) or msg <= 0)) or
                    (kind == "folder" and msg is not None)):
                    raise HTTPException(422, "Valores inconsistentes no catálogo.")
                seen.add(item_id)
                valid.append((item_id, account, kind, parent, name, size, mime, msg, created, int(trashed), int(starred)))

            mapped = {item[0]: item for item in valid}
            for item in valid:
                cursor = item[3]
                visited = {item[0]}
                while cursor and cursor in mapped:
                    if cursor in visited or mapped[cursor][2] != "folder":
                        raise HTTPException(422, "Estrutura de pastas inválida ou cíclica.")
                    visited.add(cursor)
                    cursor = mapped[cursor][3]

            with connection() as db:
                existing = {row["id"]: row for row in db.execute(
                    "SELECT id,account,kind FROM nodes").fetchall()}
                missing = [item for item in valid if item[0] not in existing]
                for item in valid:
                    matched = existing.get(item[0])
                    if matched and (matched["account"] != account or matched["kind"] != item[2]):
                        raise HTTPException(409, "Conflito com identificador de catálogo já existente.")
                    parent = item[3]
                    if parent and parent not in mapped:
                        found = db.execute("SELECT kind FROM nodes WHERE id=? AND account=?", (parent, account)).fetchone()
                        if not found or found["kind"] != "folder":
                            raise HTTPException(422, "O catálogo possui uma pasta de destino inexistente.")
                if not dry_run and missing:
                    db.executemany("""INSERT INTO nodes
                        (id,account,kind,parent,name,size,mime,message_id,created,trashed,starred)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?)""", missing)
            return {"checked": len(valid), "new_items": len(missing),
                    "existing_items": len(valid)-len(missing),
                    "imported": 0 if dry_run else len(missing),
                    "dry_run": dry_run,
                    "note": "Somente metadados. Os arquivos devem continuar no canal Telegram."}

    @router.delete("/items/{item_id}/permanent")
    async def delete_permanently(item_id: str):
        """Delete Telegram messages AND SQLite records only for items in trash."""
        async with lock:
            client, account = await authorized_account()
            cid = channel_id(channel_links, account)
            with connection() as db:
                root=db.execute("SELECT id,kind,trashed FROM nodes WHERE id=? AND account=?",(item_id,account)).fetchone()
                if not root:
                    raise HTTPException(404,"Item não encontrado.")
                if not root["trashed"]:
                    raise HTTPException(409,"Mova o item para a lixeira antes de excluir definitivamente.")
                rows=db.execute("""WITH RECURSIVE descendants(id) AS (
                    SELECT id FROM nodes WHERE id=? AND account=?
                    UNION ALL
                    SELECT n.id FROM nodes n JOIN descendants d ON n.parent=d.id WHERE n.account=?
                )
                SELECT id,kind,message_id FROM nodes WHERE account=? AND id IN (SELECT id FROM descendants)""",
                (item_id,account,account,account)).fetchall()
                ids=[row["id"] for row in rows]
                message_ids=[int(row["message_id"]) for row in rows if row["kind"]=="file" and row["message_id"] is not None]
                try:
                    if message_ids:
                        await client.delete_messages(cid,message_ids,revoke=True)
                except Exception as exc:
                    raise HTTPException(502,"Falha ao excluir no Telegram; catálogo mantido: "+type(exc).__name__) from exc
                try:
                    db.executemany("DELETE FROM nodes WHERE id=? AND account=?",[(id_,account) for id_ in ids])
                except sqlite3.Error as exc:
                    raise HTTPException(500,"Mensagens excluídas no Telegram, mas o catálogo local não foi atualizado. Não repita a exclusão sem verificar.") from exc
            return {"deleted":len(ids),"telegram_messages":len(message_ids)}

    return router
