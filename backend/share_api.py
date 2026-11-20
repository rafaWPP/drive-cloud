"""Temporary localhost sharing with revocable, scoped, expiring links.

Not a public internet sharing server. The backend is localhost-only and requires
the owner's active Telegram session to retrieve file data. Never expose the
local backend or Telegram session through an internet reverse proxy.
"""
import hashlib
import io
import os
import secrets
import sqlite3
import time
import uuid
import zipfile

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from typing import Literal

from storage_api import connection, channel_id, is_image, prepare_image

MAX_PUBLIC_ZIP = 50 * 1024 * 1024
MAX_PUBLIC_ITEMS = 100

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
    mode: Literal["download","view"] = "view"
    expires_hours: Literal[1,24,168] = 24

def build_share_router(authorized_account, channel_links, lock):
    router=APIRouter()

    async def lookup(token):
        if len(token)>256 or not token:
            raise HTTPException(404,"Link inválido")
        digest=hashlib.sha256(token.encode()).hexdigest()
        with connection() as db:
            schema(db)
            link=db.execute("""SELECT * FROM share_links WHERE token_hash=? AND revoked=0
                AND expires>?""",(digest,int(time.time()))).fetchone()
            if not link:
                raise HTTPException(404,"Link expirado ou revogado.")
            root=db.execute("SELECT * FROM nodes WHERE id=? AND account=? AND trashed=0",
                            (link["item_id"],link["owner"])).fetchone()
            if not root:
                raise HTTPException(404,"Este arquivo ou pasta não está mais disponível.")
            return dict(link), dict(root)

    def child_rows(db,root,owner):
        all_rows=[dict(r) for r in db.execute("SELECT * FROM nodes WHERE account=? AND trashed=0",(owner,))]
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
                expires=int(time.time())+body.expires_hours*3600
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
                output=[{"id":row["id"],"kind":row["kind"],"name":row["name"],
                         "size":row["size"],"path":rel} for row,rel in items[1:]]
        return {"name":root["name"],"kind":root["kind"],"size":root["size"],
                "mode":link["mode"],"expires":link["expires"],"items":output,
                "local_only":True}

    @router.get("/api/public/share/{token}/preview")
    async def preview_root(token:str):
        link,root=await lookup(token)
        if link["mode"]!="view" or root["kind"]!="file" or not is_image(root):
            raise HTTPException(415,"Prévia indisponível.")
        if root["size"]>20*1024*1024:
            raise HTTPException(413,"Imagem grande demais para prévia nesta versão.")
        async with lock:
            client,account=await authorized_account()
            if account!=link["owner"]:
                raise HTTPException(403,"Sessão Telegram indisponível.")
            msg=await client.get_messages(channel_id(channel_links,account),ids=root["message_id"])
            if not msg or not msg.media:
                raise HTTPException(404,"Imagem não encontrada.")
            data=await client.download_media(msg,file=bytes)
            if data is None:raise HTTPException(502,"Falha ao recuperar imagem.")
            return Response(prepare_image(data,1200),media_type="image/jpeg",
                headers={"Cache-Control":"no-store"})

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

    @router.get("/api/public/share/{token}/file/{file_id}")
    async def download_shared_child(token:str,file_id:str):
        link,root=await lookup(token)
        if link["mode"]!="view" or root["kind"]!="folder":
            raise HTTPException(403,"Este link não permite navegar pelos arquivos.")
        async with lock:
            client,account=await authorized_account()
            if account!=link["owner"]:raise HTTPException(403,"Conta do Telegram indisponível.")
            with connection() as db:
                items=child_rows(db,root,account)
            item=next((x for x,_ in items if x["id"]==file_id and x["kind"]=="file"),None)
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
