"""Temporary localhost sharing with revocable, scoped, expiring links.

Not a public internet sharing server. The backend is localhost-only and requires
the owner's active Telegram session to retrieve file data. Never expose the
local backend or Telegram session through an internet reverse proxy.
"""
import hashlib
import asyncio
import re
from collections import OrderedDict
import io
import os
import secrets
import sqlite3
import time
import uuid
import zipfile

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Literal

from storage_api import connection, channel_id, is_image, prepare_image, THUMBS
from media_ranges import select_range, read_exact_range, UnsatisfiableRange, ShortMediaRead

MAX_PUBLIC_ZIP = 50 * 1024 * 1024
MAX_PUBLIC_ITEMS = 100
MEDIA_STREAM_LIMIT = asyncio.Semaphore(3)
MEDIA_RANGE_CHUNK = 512 * 1024
MEDIA_RANGE_MAX = 2 * 1024 * 1024
# Playback authorization is generated when the share page is opened.
# A raw /media URL without this temporary scoped credential is not a
# shareable standalone video URL. A holder of the main share link may
# legitimately obtain a new credential; this is not DRM.
MEDIA_TICKETS = {}
MEDIA_TICKET_TTL = 7200

def issue_media_ticket(link):
    now=int(time.time())
    if len(MEDIA_TICKETS)>512:
        for key, (_,expires) in list(MEDIA_TICKETS.items()):
            if expires<=now:
                MEDIA_TICKETS.pop(key,None)
    if len(MEDIA_TICKETS)>1024:
        for key in list(MEDIA_TICKETS)[:256]:
            MEDIA_TICKETS.pop(key,None)
    ticket=secrets.token_urlsafe(32)
    digest=hashlib.sha256(ticket.encode()).hexdigest()
    MEDIA_TICKETS[digest]=(link["id"],min(link["expires"],now+MEDIA_TICKET_TTL))
    return ticket

def require_media_ticket(link,ticket):
    if not ticket or len(ticket)>160:
        raise HTTPException(403,"Abra o conteúdo pelo link compartilhado.")
    digest=hashlib.sha256(ticket.encode()).hexdigest()
    entry=MEDIA_TICKETS.get(digest)
    if not entry or entry[0]!=link["id"] or entry[1]<=time.time():
        raise HTTPException(403,"Autorização de prévia expirada. Reabra o link compartilhado.")

# Short-lived RAM cache: avoids downloading the same Telegram media for every
# browser video Range request. It never persists content on disk.
MEDIA_CACHE = OrderedDict()
MEDIA_CACHE_BYTES = 0
MEDIA_CACHE_LIMIT = 96 * 1024 * 1024
MEDIA_CACHE_TTL = 180

def cached_media_get(key):
    global MEDIA_CACHE_BYTES
    now=time.monotonic()
    for cached_key,(stamp,blob) in list(MEDIA_CACHE.items()):
        if now-stamp>MEDIA_CACHE_TTL:
            MEDIA_CACHE_BYTES-=len(blob)
            del MEDIA_CACHE[cached_key]
    entry=MEDIA_CACHE.get(key)
    if entry:
        MEDIA_CACHE.move_to_end(key)
        return entry[1]
    return None

def cached_media_put(key,blob):
    global MEDIA_CACHE_BYTES
    if len(blob)>MEDIA_CACHE_LIMIT:return
    old=MEDIA_CACHE.pop(key,None)
    if old:MEDIA_CACHE_BYTES-=len(old[1])
    while MEDIA_CACHE and MEDIA_CACHE_BYTES+len(blob)>MEDIA_CACHE_LIMIT:
        _,(_,oldblob)=MEDIA_CACHE.popitem(last=False)
        MEDIA_CACHE_BYTES-=len(oldblob)
    MEDIA_CACHE[key]=(time.monotonic(),blob)
    MEDIA_CACHE_BYTES+=len(blob)

def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS share_links(
        id TEXT PRIMARY KEY, owner TEXT NOT NULL, item_id TEXT NOT NULL,
        token_hash TEXT UNIQUE NOT NULL, mode TEXT NOT NULL,
        created INTEGER NOT NULL, expires INTEGER NOT NULL,
        revoked INTEGER NOT NULL DEFAULT 0
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS share_owner ON share_links(owner,created)")

class ShareIn(BaseModel):
    item_id: str
    mode: Literal["download","view","embed"] = "view"
    expires_hours: Literal[0,1,24,168] = 24

def build_share_router(authorized_account, channel_links, lock):
    router=APIRouter()

    async def lookup(token):
        if len(token)>256 or not token:
            raise HTTPException(404,"Link inválido.")
        digest=hashlib.sha256(token.encode()).hexdigest()
        with connection() as db:
            schema(db)
            link=db.execute("SELECT * FROM share_links WHERE token_hash=?",
                            (digest,)).fetchone()
            if not link:
                raise HTTPException(404,"Link inválido.")
            if link["revoked"]:
                raise HTTPException(410,"O proprietário revogou este compartilhamento.")
            if link["expires"]<=int(time.time()):
                raise HTTPException(410,"Este link de compartilhamento expirou.")
            root=db.execute("SELECT * FROM nodes WHERE id=? AND account=? AND trashed=0",
                            (link["item_id"],link["owner"])).fetchone()
            if not root:
                raise HTTPException(404,"Este arquivo ou pasta não está mais disponível.")
            return dict(link), dict(root)

    def child_rows(db,root,owner):
        # Fetch only the shared subtree; scanning the whole user's Drive used to
        # make even small shared folders slow when the catalog had many files.
        all_rows=[dict(r) for r in db.execute("""
            WITH RECURSIVE descendants(id,depth) AS (
                SELECT id,0 FROM nodes WHERE id=? AND account=? AND trashed=0
                UNION ALL
                SELECT n.id,d.depth+1 FROM nodes n JOIN descendants d
                ON n.parent=d.id JOIN nodes parent ON parent.id=d.id
                WHERE n.account=? AND n.trashed=0 AND parent.kind='folder'
                      AND d.depth<48
            )
            SELECT n.* FROM nodes n JOIN descendants d ON n.id=d.id
            LIMIT ?
        """,(root["id"],owner,owner,MAX_PUBLIC_ITEMS+1))]
        if len(all_rows)>MAX_PUBLIC_ITEMS:
            raise HTTPException(413,"Muitos itens nesta pasta compartilhada.")
        children={}
        for item in all_rows:
            children.setdefault(item["parent"],[]).append(item)
        stack=[(root,"")]
        output=[]
        visited=set()
        while stack:
            item,relative=stack.pop()
            if item["id"] in visited: raise HTTPException(409,"Estrutura cíclica de pastas.")
            visited.add(item["id"])
            output.append((item,relative))
            if len(output)>MAX_PUBLIC_ITEMS:
                raise HTTPException(413,"Pasta grande demais para este modo de compartilhamento.")
            if item["kind"]=="folder":
                for child in children.get(item["id"],[]):
                    child_name=child["name"].replace("/","_").replace("\\","_").replace(chr(0),"_")
                    stack.append((child,relative+child_name+("/" if child["kind"]=="folder" else "")))
        return output

    def scoped_file(db,root,owner,file_id):
        """Check a single child's ancestry instead of listing every folder item."""
        row=db.execute("""SELECT * FROM nodes WHERE id=? AND account=?
                          AND kind='file' AND trashed=0""",(file_id,owner)).fetchone()
        if not row:
            return None
        belongs=db.execute("""
            WITH RECURSIVE ancestry(id,parent,depth) AS (
              SELECT id,parent,0 FROM nodes
                WHERE id=? AND account=? AND kind='file' AND trashed=0
              UNION ALL
              SELECT parent.id,parent.parent,a.depth+1 FROM nodes parent
                JOIN ancestry a ON parent.id=a.parent
                WHERE parent.account=? AND parent.kind='folder'
                  AND parent.trashed=0 AND a.depth<48
            )
            SELECT 1 FROM ancestry WHERE id=? LIMIT 1
        """,(file_id,owner,owner,root["id"])).fetchone()
        return dict(row) if belongs else None

    @router.post("/api/share")
    async def create_share(body: ShareIn):
        async with lock:
            _,account=await authorized_account()
            channel_id(channel_links,account)
            with connection() as db:
                schema(db)
                row=db.execute("SELECT kind FROM nodes WHERE id=? AND account=? AND trashed=0",
                               (body.item_id,account)).fetchone()
                if not row: raise HTTPException(404,"Arquivo ou pasta não encontrada.")
                token=secrets.token_urlsafe(32)
                share_id=str(uuid.uuid4())
                expires=(253402300799 if body.expires_hours==0 else int(time.time())+body.expires_hours*3600)
                db.execute("""INSERT INTO share_links(id,owner,item_id,token_hash,mode,created,expires)
                    VALUES (?,?,?,?,?,?,?)""",(share_id,account,body.item_id,
                    hashlib.sha256(token.encode()).hexdigest(),body.mode,int(time.time()),expires))
            return {"id":share_id,"token":token,"mode":body.mode,
                    "expires":expires,"local_only":True}

    @router.get("/api/share")
    async def list_shares():
        async with lock:
            _,account=await authorized_account()
            channel_id(channel_links,account)
            with connection() as db:
                schema(db)
                rows=db.execute("""SELECT s.id,s.item_id,s.mode,s.created,s.expires,s.revoked,
                    n.name,n.kind FROM share_links s LEFT JOIN nodes n
                    ON n.id=s.item_id AND n.account=s.owner
                    WHERE s.owner=? ORDER BY s.created DESC LIMIT 100""",(account,)).fetchall()
            return {"links":[dict(r) for r in rows]}

    @router.delete("/api/share/{share_id}")
    async def revoke_share(share_id:str):
        async with lock:
            _,account=await authorized_account()
            with connection() as db:
                schema(db)
                cur=db.execute("UPDATE share_links SET revoked=1 WHERE id=? AND owner=?",
                               (share_id,account))
                if cur.rowcount==0:raise HTTPException(404,"Compartilhamento não encontrado.")
            return {"revoked":True}

    @router.get("/api/public/share/{token}")
    async def view_share(token:str):
        link,root=await lookup(token)
        output=[]
        if root["kind"]=="folder" and link["mode"]=="view":
            with connection() as db:
                items=child_rows(db,root,link["owner"])
                output=[{"id":row["id"],"parent":row["parent"],"kind":row["kind"],"name":row["name"],
                         "size":row["size"],"path":rel} for row,rel in items[1:]]
        return {"root_id":root["id"],"name":root["name"],"kind":root["kind"],"size":root["size"],
                "mode":link["mode"],"expires":link["expires"],"items":output,
                "media_ticket":issue_media_ticket(link) if link["mode"] in ("view","embed") else None,
                "local_only":True}

    @router.get("/api/public/share/{token}/download")
    async def download_root(token:str):
        link,root=await lookup(token)
        async with lock:
            client,account=await authorized_account()
            if account!=link["owner"]:raise HTTPException(403,"Conta do Telegram indisponível.")
            cid=channel_id(channel_links,account)
            if root["kind"]=="file":
                msg=await client.get_messages(cid,ids=root["message_id"])
                if not msg or not msg.media:raise HTTPException(404,"Arquivo ausente do canal.")
                data=await client.download_media(msg,file=bytes)
                if data is None:raise HTTPException(502,"Falha ao recuperar arquivo.")
                if len(data)>MAX_PUBLIC_ZIP:raise HTTPException(413,"Arquivo grande demais para link de teste.")
                name=root["name"].replace("/","_").replace("\\","_")
                from urllib.parse import quote
                return Response(data,media_type="application/octet-stream",
                    headers={"Cache-Control":"no-store","Content-Disposition":
                        "attachment; filename*=UTF-8''"+quote(name)})
            with connection() as db:
                items=child_rows(db,root,account)
            if sum(x["size"] for x,_ in items if x["kind"]=="file")>MAX_PUBLIC_ZIP:
                raise HTTPException(413,"Pasta maior que 50 MB para download por link nesta versão.")
            output=io.BytesIO()
            processed=0
            with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED,compresslevel=5) as archive:
                base=root["name"].replace("/","_").replace("\\","_")+"/"
                used=set()
                for row,relative in items:
                    archive_name=base+relative
                    if archive_name in used:raise HTTPException(409,"Nomes duplicados na pasta.")
                    used.add(archive_name)
                    if row["kind"]=="folder":
                        archive.writestr(archive_name,b"")
                    else:
                        msg=await client.get_messages(cid,ids=row["message_id"])
                        if not msg or not msg.media:raise HTTPException(404,"Arquivo ausente: "+row["name"])
                        data=await client.download_media(msg,file=bytes)
                        if data is None:raise HTTPException(502,"Falha ao recuperar arquivo.")
                        processed+=len(data)
                        if processed>MAX_PUBLIC_ZIP:raise HTTPException(413,"Tamanho real da pasta excede o limite de 50 MB.")
                        archive.writestr(archive_name,data)
            from urllib.parse import quote
            return Response(output.getvalue(),media_type="application/zip",
                headers={"Cache-Control":"no-store","Content-Disposition":
                    "attachment; filename*=UTF-8''"+quote(root["name"]+".zip")})

    def safe_media_type(item):
        """Only render ordinary browser-safe media; everything else stays a download."""
        import mimetypes
        name=str(item["name"]).lower()
        ext=name.rsplit(".",1)[-1] if "." in name else ""
        supported={"jpg":"image/jpeg","jpeg":"image/jpeg","png":"image/png",
                   "webp":"image/webp","gif":"image/gif",
                   "mp4":"video/mp4","webm":"video/webm","m4v":"video/mp4",
                   "jxl":"image/jpeg","bmp":"image/jpeg","tif":"image/jpeg","tiff":"image/jpeg"}
        return supported.get(ext)

    async def send_media(link,root,request:Request,item_id=None,thumb=False):
        require_media_ticket(link,request.query_params.get("access"))
        # A media URL is an internal resource, not a second share page. Browsing
        # directly to this endpoint is blocked; media/image elements still work.
        # This is a UI guard, NOT DRM: share-token holders can retrieve file bytes.
        if request.headers.get("sec-fetch-dest") in ("document","frame","iframe"):
            raise HTTPException(403,"Abra a mídia pela página de compartilhamento.")
        if link["mode"] not in ("view","embed"):
            raise HTTPException(403,"Este link não permite visualizar mídia.")
        if item_id:
            if root["kind"]!="folder" or link["mode"]!="view":
                raise HTTPException(403,"Arquivo fora da pasta compartilhada.")
            with connection() as db:
                item=scoped_file(db,root,link["owner"],item_id)
            if item is None:
                raise HTTPException(404,"Arquivo fora do compartilhamento.")
        else:
            item=root
        media_type=safe_media_type(item)
        if not media_type or item["kind"]!="file":
            raise HTTPException(415,"Prévia indisponível para este formato.")
        if thumb and not media_type.startswith("image/"):
            raise HTTPException(415,"Miniatura não disponível para este arquivo.")
        if int(item["size"])>MAX_PUBLIC_ZIP:
            raise HTTPException(413,"Mídia excede o limite de prévia de 50 MB.")

        async with lock:
            client,account=await authorized_account()
            if account!=link["owner"]:
                raise HTTPException(403,"Conta Telegram do proprietário desconectada.")
            cid=channel_id(channel_links,account)
            media_key=(account,cid,item["message_id"],str(item["id"]))
            derived_key=media_key+("thumb",)
            data=cached_media_get(derived_key if thumb else media_key)
            msg=None
            # Message lookup is quick. Do not hold the global lock throughout
            # downloading or streaming: other navigation must remain responsive.
            if data is None:
                msg=await client.get_messages(cid,ids=item["message_id"])
                if not msg or not msg.media:
                    raise HTTPException(404,"Arquivo não encontrado no Telegram.")
        if thumb:
            if data is None:
                # Existing Drive derivative may already be cached on disk.
                key=hashlib.sha256((account+":"+str(item["id"])+":"+
                                   str(item["message_id"])+":False").encode()).hexdigest()
                derivative=THUMBS/(key+".jpg")
                if derivative.exists():
                    data=derivative.read_bytes()
                else:
                    raw=None
                    has_thumbs=(getattr(getattr(msg,"document",None),"thumbs",None)
                                or getattr(getattr(msg,"photo",None),"sizes",None))
                    if has_thumbs:
                        try:
                            raw=await client.download_media(msg,file=bytes,thumb=-1)
                            if raw:
                                data=prepare_image(raw,420)
                        except (HTTPException,ValueError,TypeError,OSError):
                            data=None
                    if data is None:
                        raw=cached_media_get(media_key)
                        if raw is None:
                            raw=await client.download_media(msg,file=bytes)
                        if not raw:
                            raise HTTPException(502,"Não foi possível preparar miniatura.")
                        data=prepare_image(raw,420)
                    # Derivatives contain no original byte payload.
                    try:
                        derivative.write_bytes(data)
                    except OSError:
                        pass
                cached_media_put(derived_key,data)
            return Response(data,media_type="image/jpeg",
                            headers={"Cache-Control":"private, no-store",
                                     "X-Content-Type-Options":"nosniff"})

        is_video=media_type.startswith("video/")
        if is_video:
            total=(int(getattr(getattr(msg,"file",None),"size",0) or item["size"])
                   if msg else len(data))
            if total<=0 or total>MAX_PUBLIC_ZIP:
                raise HTTPException(413,"Vídeo com tamanho inválido para prévia.")
            try:
                start,end,is_range=select_range(
                    request.headers.get("range"),total,MEDIA_RANGE_MAX
                )
            except UnsatisfiableRange:
                raise HTTPException(416,"Intervalo solicitado é inválido.",
                                    headers={"Content-Range":f"bytes */{total}"})
            headers={"Accept-Ranges":"bytes","Cache-Control":"private, no-store",
                     "X-Content-Type-Options":"nosniff"}
            if is_range:
                headers["Content-Range"]=f"bytes {start}-{end}/{total}"

            if data is None:
                # Prefetch the exact section from Telegram BEFORE an HTTP 206
                # begins. This prevents ASGI streaming exceptions from killing
                # the player's response mid-transfer. Limit concurrency/RAM.
                try:
                    async with MEDIA_STREAM_LIMIT:
                        # A Telegram Document is a supported iter_download input.
                        media=getattr(msg,"document",None) or msg
                        data=await read_exact_range(
                            client,media,start,end-start+1
                        )
                except ShortMediaRead as exc:
                    raise HTTPException(502,
                        "Telegram enviou um trecho incompleto do vídeo. "
                        "Tente novamente.") from exc
                except Exception as exc:
                    raise HTTPException(502,
                        "Falha ao buscar trecho do vídeo no Telegram. "
                        "Confira o backend.") from exc
            else:
                data=data[start:end+1]

            if len(data)!=end-start+1:
                raise HTTPException(502,"Tamanho incorreto do trecho do vídeo.")
            # Response computes Content-Length from the actual bytes, so it
            # cannot disagree with the transmitted body.
            return Response(data,
                            status_code=206 if is_range else 200,
                            media_type=media_type,headers=headers)

        # For images, preserve the existing short-lived RAM cache. Conversion
        # is only needed for formats browsers cannot display natively.
        if data is None:
            data=await client.download_media(msg,file=bytes)
            if data is None:
                raise HTTPException(502,"Falha ao recuperar imagem.")
            if len(data)>MAX_PUBLIC_ZIP:
                raise HTTPException(413,"Imagem grande demais para prévia.")
            if str(item["name"]).lower().endswith((".jxl",".bmp",".tif",".tiff")):
                data=prepare_image(data,1800)
            cached_media_put(media_key,data)
        return Response(data,media_type=media_type,
                        headers={"Cache-Control":"private, no-store",
                                 "X-Content-Type-Options":"nosniff"})

    @router.get("/api/public/share/{token}/media-status")
    async def media_status(token:str,file_id:str|None=None):
        """Lightweight diagnostic for broken previews, scoped to a valid share token."""
        link,root=await lookup(token)
        if link["mode"] not in ("view","embed"):
            raise HTTPException(403,"Este link não autoriza visualização de mídia.")
        target=root
        if file_id:
            if root["kind"]!="folder" or link["mode"]!="view":
                raise HTTPException(403,"Arquivo fora do compartilhamento.")
            with connection() as db:
                target=scoped_file(db,root,link["owner"],file_id)
            if not target:
                raise HTTPException(404,"Arquivo não encontrado neste compartilhamento.")
        if target["kind"]!="file" or not safe_media_type(target):
            raise HTTPException(415,"Formato sem prévia no navegador. Utilize o download.")
        if target["size"]>MAX_PUBLIC_ZIP:
            raise HTTPException(413,"A prévia local aceita arquivos de até 50 MB.")
        async with lock:
            client,account=await authorized_account()
            if account!=link["owner"]:
                raise HTTPException(403,"A conta Telegram proprietária não está conectada.")
            message=await client.get_messages(channel_id(channel_links,account),ids=target["message_id"])
            if not message or not message.media:
                raise HTTPException(404,"O arquivo não está mais disponível no canal Telegram.")
        return {"ready":True,"name":target["name"],"type":safe_media_type(target)}

    @router.get("/api/public/share/{token}/media")
    async def media_root(token:str,request:Request,thumb:bool=False):
        link,root=await lookup(token)
        return await send_media(link,root,request,thumb=thumb)

    @router.get("/api/public/share/{token}/media/{file_id}")
    async def media_child(token:str,file_id:str,request:Request,thumb:bool=False):
        link,root=await lookup(token)
        return await send_media(link,root,request,file_id,thumb=thumb)

    @router.get("/api/public/share/{token}/file/{file_id}")
    async def download_shared_child(token:str,file_id:str):
        link,root=await lookup(token)
        if link["mode"]!="view" or root["kind"]!="folder":
            raise HTTPException(403,"Este link não permite navegar pelos arquivos.")
        async with lock:
            client,account=await authorized_account()
            if account!=link["owner"]:raise HTTPException(403,"Conta do Telegram indisponível.")
            with connection() as db:
                item=scoped_file(db,root,account,file_id)
            if not item:raise HTTPException(404,"Arquivo não incluído neste link.")
            msg=await client.get_messages(channel_id(channel_links,account),ids=item["message_id"])
            if not msg or not msg.media:raise HTTPException(404,"Arquivo ausente.")
            data=await client.download_media(msg,file=bytes)
            if data is None:raise HTTPException(502,"Falha ao recuperar arquivo.")
            if len(data)>MAX_PUBLIC_ZIP:raise HTTPException(413,"Arquivo grande demais para link de teste.")
            from urllib.parse import quote
            return Response(data,media_type="application/octet-stream",
                headers={"Cache-Control":"no-store","Content-Disposition":
                    "attachment; filename*=UTF-8''"+quote(item["name"])})

    return router
