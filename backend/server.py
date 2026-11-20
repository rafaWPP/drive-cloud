"""Integração Telegram local: somente autenticação (sem uploads nesta etapa)."""
import asyncio
import base64
import io
import json
import os
import re
from pathlib import Path
from telethon.tl.functions.channels import CreateChannelRequest
from telethon.tl.types import Channel

import qrcode
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from telethon import TelegramClient, errors

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DATA = ROOT / ".data"
DATA.mkdir(mode=0o700, exist_ok=True)
try:
    DATA.chmod(0o700)
except OSError:
    pass

API_ID = int(os.environ.get("TELEGRAM_API_ID") or 0)
API_HASH = os.environ.get("TELEGRAM_API_HASH", "").strip()
app = FastAPI(title="Drive Cloud - Telegram local", docs_url=None, redoc_url=None)
ALLOWED = {"http://127.0.0.1:5173", "http://localhost:5173"}
app.add_middleware(CORSMiddleware, allow_origins=list(ALLOWED), allow_credentials=False,
                   allow_methods=["GET", "POST", "PATCH", "DELETE"], allow_headers=["Content-Type"])
client = None
phone_pending = None
phone_code_hash = None
lock = asyncio.Lock()
qr_login = None
qr_task = None
qr_state = 'idle'
qr_error = None

class PhoneIn(BaseModel):
    phone: str = Field(min_length=8, max_length=25)

class CodeIn(BaseModel):
    code: str = Field(min_length=3, max_length=12)

class PasswordIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)

@app.middleware("http")
async def local_only(request: Request, call_next):
    host = request.client.host if request.client else ""
    if host not in {"127.0.0.1", "::1"}:
        raise HTTPException(status_code=403, detail="Acesso permitido somente neste PC")
    if request.method != "GET":
        origin = request.headers.get("origin")
        if origin not in ALLOWED:
            raise HTTPException(status_code=403, detail="Origem não autorizada")
    return await call_next(request)

def configured():
    if not API_ID or not API_HASH:
        raise HTTPException(status_code=422, detail="Configure TELEGRAM_API_ID e TELEGRAM_API_HASH em backend/.env")

async def connected_client():
    global client
    configured()
    if client is None:
        client = TelegramClient(str(DATA / "telegram"), API_ID, API_HASH, receive_updates=True)
    if not client.is_connected():
        await client.connect()
    return client

def response_user(user):
    return {"connected": True, "name": " ".join(filter(None, [user.first_name, user.last_name])),
            "username": user.username, "id": user.id}

@app.get("/api/telegram/status")
async def status():
    if not API_ID or not API_HASH:
        return {"connected": False, "configured": False}
    async with lock:
        try:
            c = await connected_client()
            if await c.is_user_authorized():
                return {"configured": True, **response_user(await c.get_me())}
            return {"connected": False, "configured": True}
        except Exception:
            return {"connected": False, "configured": True, "error": "Não foi possível consultar o Telegram"}


@app.get("/api/telegram/avatar")
async def telegram_avatar():
    """Only serves the logged-in account photo on the local backend."""
    from fastapi.responses import Response
    async with lock:
        c, _ = await authorized_account()
        me = await c.get_me()
        if not getattr(me, "photo", None):
            raise HTTPException(404, "Esta conta não possui foto de perfil.")
        raw = await c.download_profile_photo(me, file=bytes)
        if not raw:
            raise HTTPException(404, "Não foi possível recuperar a foto de perfil.")
        if len(raw) > 2 * 1024 * 1024:
            raise HTTPException(413, "Foto de perfil muito grande.")
        return Response(raw, media_type="image/jpeg",
                        headers={"Cache-Control":"private, no-store",
                                 "X-Content-Type-Options":"nosniff"})

def qr_image(url):
    img = qrcode.make(url)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

async def wait_for_qr(login):
    global qr_state, qr_error
    try:
        await login.wait()
        qr_state = "connected"
    except errors.SessionPasswordNeededError:
        qr_state = "password"
    except asyncio.TimeoutError:
        qr_state = "expired"
    except asyncio.CancelledError:
        raise
    except Exception:
        qr_error = "Falha ao autorizar QR Code. Gere outro código."
        qr_state = "error"

async def cancel_qr():
    global qr_login, qr_task, qr_state, qr_error
    if qr_task and not qr_task.done():
        qr_task.cancel()
        try:
            await qr_task
        except asyncio.CancelledError:
            pass
    qr_task = None
    qr_login = None
    qr_state = "idle"
    qr_error = None

# O canal é criado somente depois da autorização, por solicitação do frontend.
# O vínculo é separado por ID do usuário Telegram. Não são enviados arquivos aqui.
CHANNEL_TITLE = "Drive Cloud Storage"
CHANNEL_MARKER = "Canal privado de armazenamento do Drive Cloud. Não exclua este canal."
CHANNEL_FILE = DATA / "storage_channels.json"

def channel_links():
    if not CHANNEL_FILE.exists():
        return {}
    try:
        with CHANNEL_FILE.open("r", encoding="utf-8") as file:
            entries = json.load(file)
        if not isinstance(entries, dict):
            raise ValueError("Formato incorreto")
        return entries
    except (OSError, ValueError) as exc:
        # Não recriar o canal se não conseguirmos ler seu vínculo anterior.
        raise HTTPException(500, detail="Falha ao ler vínculo local do canal. Verifique backend/.data antes de continuar.") from exc

def save_channel_links(links):
    temp = CHANNEL_FILE.with_suffix(".tmp")
    try:
        with temp.open("w", encoding="utf-8") as file:
            json.dump(links, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, CHANNEL_FILE)
    except OSError as exc:
        raise HTTPException(500, detail="Não foi possível salvar o vínculo com o canal Telegram.") from exc

async def authorized_account():
    c = await connected_client()
    if not await c.is_user_authorized():
        raise HTTPException(401, detail="Conecte sua conta Telegram antes de configurar o armazenamento.")
    me = await c.get_me()
    return c, str(me.id)

def channel_info(channel, created=False):
    return {"ready": True, "channel_id": str(channel.id),
            "title": channel.title, "created": created}

@app.get("/api/telegram/storage/status")
async def storage_status():
    async with lock:
        c, user_id = await authorized_account()
        entry = channel_links().get(user_id)
        if not entry:
            return {"ready": False, "state": "not_configured"}
        try:
            channel = await c.get_entity(int(entry["channel_id"]))
            if not isinstance(channel, Channel) or not channel.broadcast:
                raise ValueError("Não é um canal")
            return channel_info(channel)
        except (ValueError, TypeError, errors.RPCError):
            return {"ready": False, "state": "missing", "detail": "Canal associado não está acessível. Nenhum novo canal será criado automaticamente."}

@app.post("/api/telegram/storage/ensure")
async def ensure_storage():
    async with lock:
        c, user_id = await authorized_account()
        links = channel_links()
        entry = links.get(user_id)
        if entry:
            try:
                entity = await c.get_entity(int(entry["channel_id"]))
                if not isinstance(entity, Channel) or not entity.broadcast:
                    raise ValueError("O vínculo aponta para outra entidade")
                return channel_info(entity)
            except (ValueError, TypeError, errors.RPCError):
                raise HTTPException(409, detail="Seu canal já foi registrado, mas não está acessível. Verifique o Telegram; não criaremos um duplicado.")
        # Recuperação após falha entre a criação e a gravação local: localizar
        # um canal próprio com título e descrição específicos antes de criar.
        try:
            matches = []
            async for dialog in c.iter_dialogs():
                entity = dialog.entity
                if isinstance(entity, Channel) and entity.broadcast and entity.creator and entity.title == CHANNEL_TITLE:
                    matches.append(entity)
            if len(matches) == 1:
                channel = matches[0]
                links[user_id] = {"channel_id": str(channel.id)}
                save_channel_links(links)
                return channel_info(channel)
            if len(matches) > 1:
                raise HTTPException(409, detail="Encontrados vários canais com o nome Drive Cloud Storage. Resolva a duplicidade manualmente antes de continuar.")
            result = await c(CreateChannelRequest(title=CHANNEL_TITLE, about=CHANNEL_MARKER, broadcast=True, megagroup=False))
            channel = next((item for item in result.chats if isinstance(item, Channel)), None)
            if channel is None:
                raise HTTPException(502, detail="O Telegram não retornou o canal criado.")
            links[user_id] = {"channel_id": str(channel.id)}
            save_channel_links(links)
            return channel_info(channel, created=True)
        except errors.FloodWaitError as exc:
            raise HTTPException(429, detail=f"Limite do Telegram. Tente novamente em {exc.seconds} segundos.") from exc
        except errors.RPCError as exc:
            raise HTTPException(502, detail="O Telegram não permitiu criar/verificar o canal: " + type(exc).__name__) from exc

@app.post("/api/telegram/qr/start")
async def start_qr():
    global qr_login, qr_task, qr_state
    async with lock:
        c = await connected_client()
        if await c.is_user_authorized():
            return {"step": "connected", **response_user(await c.get_me())}
        await cancel_qr()
        try:
            qr_login = await c.qr_login()
            qr_state = "waiting"
            qr_task = asyncio.create_task(wait_for_qr(qr_login))
            return {"step": "qr", "image": qr_image(qr_login.url),
                    "expires": qr_login.expires.isoformat()}
        except errors.RPCError as e:
            raise HTTPException(400, detail="Telegram recusou a criação do QR Code: "+type(e).__name__)

@app.get("/api/telegram/qr/status")
async def qr_status():
    async with lock:
        if not API_ID or not API_HASH:
            return {"step": "not_configured"}
        if qr_state == "password":
            return {"step": "password"}
        if qr_state == "waiting" and qr_login and qr_login.expires.timestamp() <= __import__('time').time():
            return {"step": "expired"}
        if qr_state == "error":
            return {"step": "error", "detail": qr_error}
        if qr_state == "connected":
            c = await connected_client()
            return {"step": "connected", **response_user(await c.get_me())}
        return {"step": qr_state}

@app.post("/api/telegram/qr/password")
async def qr_password(payload: PasswordIn):
    global qr_state
    async with lock:
        if qr_state != "password":
            raise HTTPException(409, detail="O Telegram ainda não solicitou senha de duas etapas")
        try:
            c = await connected_client()
            user = await c.sign_in(password=payload.password)
            qr_state = "connected"
            return {"step": "connected", **response_user(user)}
        except errors.RPCError as e:
            raise HTTPException(400, detail="Senha recusada pelo Telegram: "+type(e).__name__)

@app.post("/api/telegram/send-code")
async def send_code(payload: PhoneIn):
    global phone_pending, phone_code_hash
    if not re.fullmatch(r"\+[1-9]\d{7,14}", payload.phone):
        raise HTTPException(422, detail="Use telefone internacional, por exemplo +5511999999999")
    async with lock:
        try:
            c = await connected_client()
            if await c.is_user_authorized():
                return {"step": "connected", **response_user(await c.get_me())}
            sent = await c.send_code_request(payload.phone)
            phone_pending = payload.phone
            phone_code_hash = sent.phone_code_hash
            return {"step": "code"}
        except errors.FloodWaitError as e:
            raise HTTPException(429, detail=f"Limite do Telegram: tente novamente em {e.seconds} segundos")
        except errors.RPCError as e:
            raise HTTPException(400, detail=f"Telegram recusou a solicitação: {type(e).__name__}")

@app.post("/api/telegram/verify-code")
async def verify_code(payload: CodeIn):
    global phone_pending, phone_code_hash
    async with lock:
        if not phone_pending or not phone_code_hash:
            raise HTTPException(409, detail="Solicite um código primeiro")
        try:
            c = await connected_client()
            user = await c.sign_in(phone=phone_pending, code=payload.code.strip(), phone_code_hash=phone_code_hash)
            phone_pending = phone_code_hash = None
            return {"step": "connected", **response_user(user)}
        except errors.SessionPasswordNeededError:
            return {"step": "password"}
        except errors.RPCError as e:
            raise HTTPException(400, detail=f"Código recusado: {type(e).__name__}")

@app.post("/api/telegram/verify-password")
async def verify_password(payload: PasswordIn):
    global phone_pending, phone_code_hash
    async with lock:
        if not phone_pending:
            raise HTTPException(409, detail="Inicie o login por telefone primeiro")
        try:
            c = await connected_client()
            user = await c.sign_in(password=payload.password)
            phone_pending = phone_code_hash = None
            return {"step": "connected", **response_user(user)}
        except errors.RPCError as e:
            raise HTTPException(400, detail=f"Não foi possível verificar a senha: {type(e).__name__}")

@app.post("/api/telegram/disconnect")
async def disconnect():
    global client, phone_pending, phone_code_hash
    async with lock:
        await cancel_qr()
        if client:
            await client.disconnect()
        client = None
        phone_pending = phone_code_hash = None
        return {"connected": False}

@app.post("/api/telegram/logout")
async def logout():
    global client, phone_pending, phone_code_hash
    async with lock:
        await cancel_qr()
        try:
            if client:
                if not client.is_connected():
                    await client.connect()
                if await client.is_user_authorized():
                    await client.log_out()
                else:
                    await client.disconnect()
        except errors.RPCError:
            raise HTTPException(400, detail="Não foi possível revogar sessão no Telegram")
        finally:
            client = None
            phone_pending = phone_code_hash = None
        session_path = DATA / "telegram.session"
        if session_path.exists():
            session_path.unlink()
        return {"connected": False}

@app.on_event("shutdown")
async def shutdown():
    await cancel_qr()
    if client and client.is_connected():
        await client.disconnect()

# Rotas locais de arquivos; usam a mesma sessão, vínculo de canal e trava de conta.
from storage_api import build_router
from backup_api import build_backup_router, backup_scheduler
from share_api import build_share_router
app.include_router(build_router(authorized_account, channel_links, lock))
app.include_router(build_backup_router(authorized_account, channel_links, lock))
app.include_router(build_share_router(authorized_account, channel_links, lock))

@app.on_event("startup")
async def start_catalog_backup_scheduler():
    app.state.catalog_backup_task = asyncio.create_task(
        backup_scheduler(authorized_account, channel_links, lock)
    )

@app.on_event("shutdown")
async def stop_catalog_backup_scheduler():
    task = getattr(app.state, "catalog_backup_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
