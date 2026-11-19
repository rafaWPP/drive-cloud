"""Integração Telegram local: somente autenticação (sem uploads nesta etapa)."""
import asyncio
import os
import re
from pathlib import Path

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
                   allow_methods=["GET", "POST"], allow_headers=["Content-Type"])
client = None
phone_pending = None
phone_code_hash = None
lock = asyncio.Lock()

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
        client = TelegramClient(str(DATA / "telegram"), API_ID, API_HASH, receive_updates=False)
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
            raise HTTPException(409, detail="Inicie o login primeiro")
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
        if client:
            await client.disconnect()
        client = None
        phone_pending = phone_code_hash = None
        return {"connected": False}

@app.post("/api/telegram/logout")
async def logout():
    global client, phone_pending, phone_code_hash
    async with lock:
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
    if client and client.is_connected():
        await client.disconnect()
