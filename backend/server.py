"""Integração Telegram local: somente autenticação (sem uploads nesta etapa)."""
import asyncio
import base64
import io
import json
import os
import re
import sqlite3
from pathlib import Path
from telethon.tl.functions.channels import CreateChannelRequest, EditPhotoRequest
from telethon.tl.types import Channel, InputChatUploadedPhoto, ChatPhotoEmpty
from channel_brand import channel_avatar_jpeg

import qrcode
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from telethon import TelegramClient, errors

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")
DATA = Path(os.environ["DRIVE_CLOUD_DATA_DIR"]).expanduser() if os.environ.get("DRIVE_CLOUD_DATA_DIR") else ROOT / ".data"
DATA.mkdir(mode=0o700, exist_ok=True)
try:
    DATA.chmod(0o700)
except OSError:
    pass

# Load credentials saved by the installed application before initializing Telethon.
# Values in the app-specific data directory take precedence over the developer .env.
load_dotenv(DATA / ".env", override=True)

API_ID = int(os.environ.get("TELEGRAM_API_ID") or 0)
API_HASH = os.environ.get("TELEGRAM_API_HASH", "").strip()
app = FastAPI(title="Drive Cloud - Telegram local", docs_url=None, redoc_url=None)
ALLOWED = {"http://127.0.0.1:5173", "http://localhost:5173", "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost"}
app.add_middleware(CORSMiddleware, allow_origins=list(ALLOWED), allow_credentials=False,
                   allow_methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "Range"],
                   expose_headers=["Content-Length", "Content-Range", "Accept-Ranges", "Content-Disposition"])
client = None
phone_pending = None
phone_code_hash = None
lock = asyncio.Lock()
qr_login = None
qr_task = None
qr_state = 'idle'
qr_error = None

class CredentialsIn(BaseModel):
    api_id: int = Field(gt=0, le=2147483647)
    api_hash: str = Field(min_length=32, max_length=32, pattern=r"^[a-fA-F0-9]{32}$")

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

@app.get("/api/health")
async def health():
    """Fast local readiness probe, independent of Telegram network/login."""
    return {"ready": True}


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

async def release_failed_session_client():
    """Release any SQLite handle left by a failed Telethon status check.

    This never calls log_out() or deletes the .session file. If a legacy
    backend process is still using the database, the next status request
    remains blocked until that process exits; do not try to kill it here.
    """
    global client
    failed = client
    client = None
    if failed is None:
        return
    try:
        await failed.disconnect()
    except Exception:
        pass
    # Telethon's SQLiteSession.close() is safe to call a second time after
    # disconnect and avoids keeping an opened DB connection on an error path.
    try:
        session = getattr(failed, "session", None)
        if session is not None:
            session.close()
    except Exception:
        pass


def response_user(user):
    return {"connected": True, "name": " ".join(filter(None, [user.first_name, user.last_name])),
            "username": user.username, "id": user.id}

def safe_session_status_error(exc):
    """Diagnose known SQLite failures without disclosing session database data.

    A local SQLite failure is not evidence that the user logged out.
    Never delete/rebuild the Telethon session as an automatic fix.
    """
    if isinstance(exc, sqlite3.Error):
        message = str(exc).lower()
        if "locked" in message or "busy" in message:
            return {
                "code": "SESSION_DATABASE_BUSY",
                "error": "O banco de sessão Telegram está ocupado por outro processo (SESSION_DATABASE_BUSY). "
                         "Feche todas as janelas do Drive Cloud e verifique se ficou algum "
                         "processo drive-cloud-backend em execução. Encerre apenas o "
                         "processo antigo, depois abra o aplicativo novamente. "
                         "Nunca exclua o arquivo telegram.session.",
            }
        if any(word in message for word in ("readonly", "read-only", "permission denied")):
            return {
                "code": "SESSION_READ_ONLY",
                "error": "O banco de sessão Telegram está sem permissão de escrita (SESSION_READ_ONLY). "
                         "Verifique as permissões da pasta de dados do Drive Cloud. "
                         "Não exclua o arquivo de sessão.",
            }
        if any(word in message for word in ("disk i/o", "disk is full", "database or disk is full",
                                            "unable to open database file", "no space left")):
            return {
                "code": "SESSION_STORAGE_ERROR",
                "error": "Falha de leitura/gravação ou espaço no disco do banco Telegram (SESSION_STORAGE_ERROR). "
                         "Verifique o espaço livre e a pasta de dados. A sessão não foi apagada.",
            }
        if any(word in message for word in ("malformed", "not a database", "database disk image")):
            return {
                "code": "SESSION_INTEGRITY_ERROR",
                "error": "O banco de sessão Telegram apresenta problema de integridade "
                         "(SESSION_INTEGRITY_ERROR). Preserve o arquivo original e faça uma cópia "
                         "antes de qualquer tentativa de recuperação.",
            }
        return {
            "code": "SESSION_SQLITE_ERROR",
            "error": "Não foi possível acessar o banco local da sessão Telegram "
                     "(SESSION_SQLITE_ERROR: " + type(exc).__name__ + "). "
                     "Os arquivos não foram alterados.",
        }
    return {
        "code": "TELEGRAM_CHECK_ERROR",
        "error": "Falha temporária ao verificar a sessão Telegram ("
                 + type(exc).__name__ + "). "
                 "Não significa que a conta foi desconectada. "
                 "Verifique a conexão e tente novamente.",
    }


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
        except sqlite3.Error as exc:
            # A failed local DB connection must not be held indefinitely by
            # this backend. Another (legacy) process may still own the lock.
            diagnostic = safe_session_status_error(exc)
            await release_failed_session_client()
            return {"connected": False, "configured": True, **diagnostic}
        except Exception as exc:
            # Never present an unverified session as a logout.
            return {"connected": False, "configured": True, **safe_session_status_error(exc)}


@app.post("/api/telegram/credentials")
async def save_credentials(payload: CredentialsIn):
    """Store user-supplied Telegram app keys on this device only.

    No secret is returned to the UI or written to logs. The installed app
    uses its own persistent DATA directory; the developer backend also
    supports this without changing backend/.env.
    """
    global API_ID, API_HASH, client
    async with lock:
        if client is not None and client.is_connected() and await client.is_user_authorized():
            raise HTTPException(409, detail="Desconecte e saia da conta Telegram antes de alterar as credenciais.")
        new_hash = payload.api_hash.strip().lower()
        config_path = DATA / ".env"
        temp_path = DATA / ".env.tmp"
        try:
            with temp_path.open("w", encoding="utf-8") as stream:
                os.chmod(temp_path, 0o600)
                stream.write(f"TELEGRAM_API_ID={payload.api_id}\\nTELEGRAM_API_HASH={new_hash}\\n".replace("\\n", "\n"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, config_path)
            os.chmod(config_path, 0o600)
        except OSError as exc:
            temp_path.unlink(missing_ok=True)
            raise HTTPException(500, detail="Não foi possível salvar as credenciais neste dispositivo.") from exc
        if client is not None:
            await client.disconnect()
            client = None
        API_ID = payload.api_id
        API_HASH = new_hash
        return {"configured": True, "connected": False}

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

async def assign_drive_channel_logo(client, channel):
    """Brand an unpictured channel without replacing a user's chosen avatar.

    Channel creation has already been persisted before calling this method.
    If Telegram rejects a photo update, channel storage remains usable.
    """
    if not getattr(channel, "creator", False):
        return False
    current_photo = getattr(channel, "photo", None)
    if current_photo is not None and not isinstance(current_photo, ChatPhotoEmpty):
        return False
    try:
        photo_bytes = io.BytesIO(channel_avatar_jpeg())
        photo_bytes.name = "drive-cloud-channel.jpg"
        uploaded = await client.upload_file(photo_bytes)
        await client(EditPhotoRequest(
            channel=channel, photo=InputChatUploadedPhoto(file=uploaded)
        ))
        return True
    except Exception:
        # Branding is cosmetic: never block account setup or create another channel.
        return False


def channel_has_public_username(channel):
    """A Telegram channel with an active public username cannot be a private
    Drive Cloud storage destination, even if its visible title matches.
    """
    if getattr(channel, "username", None):
        return True
    return any(
        getattr(entry, "active", False) and getattr(entry, "username", None)
        for entry in (getattr(channel, "usernames", None) or [])
    )


async def locate_storage_channels(client, linked_id=None):
    """Resolve an existing private channel from dialogs even when Telethon's
    in-memory entity cache is empty after restart.

    With a recorded ID we *never* fall back to some other same-named channel:
    a missing ID is an explicit error, not permission to create another one.
    """
    matches = []
    async for dialog in client.iter_dialogs():
        entity = dialog.entity
        if not isinstance(entity, Channel) or not entity.broadcast:
            continue
        if linked_id is not None:
            if entity.id == linked_id:
                return [entity]
        elif entity.creator and entity.title == CHANNEL_TITLE:
            if channel_has_public_username(entity):
                raise HTTPException(409, detail="Já existe um canal Drive Cloud Storage público na sua conta. "
                                                "Por segurança, não vamos usá-lo nem criar outro automaticamente.")
            matches.append(entity)
    return [] if linked_id is not None else matches


async def linked_storage_channel(client, entry):
    try:
        recorded_id = int(entry["channel_id"])
    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(409, detail="O vínculo salvo do canal é inválido. Seus dados foram preservados; o Drive Cloud não criará outro canal.") from exc
    if recorded_id <= 0:
        raise HTTPException(409, detail="O identificador do canal salvo é inválido. Nenhum outro canal será criado.")
    entity = None
    try:
        entity = await client.get_entity(recorded_id)
    except errors.FloodWaitError:
        raise
    except (ValueError, TypeError, errors.RPCError):
        # Missing access hash in the Telethon cache is common after restarting
        # a desktop sidecar. Listing dialogs rehydrates the input entity.
        matches = await locate_storage_channels(client, linked_id=recorded_id)
        entity = matches[0] if matches else None
    if not isinstance(entity, Channel) or not entity.broadcast or entity.id != recorded_id:
        raise HTTPException(
            409, detail="O canal privado já está vinculado, mas não foi encontrado na conta Telegram conectada. "
                        "Confirme que é a mesma conta. Nenhum canal será criado ou excluído.",
        )
    if channel_has_public_username(entity):
        raise HTTPException(409, detail="O canal vinculado tem endereço público no Telegram. "
                                        "Para proteger seus arquivos, o Drive Cloud não o utilizará como armazenamento privado.")
    return entity


@app.get("/api/telegram/storage/status")
async def storage_status():
    async with lock:
        c, user_id = await authorized_account()
        entry = channel_links().get(user_id)
        if not entry:
            return {"ready": False, "state": "not_configured",
                    "detail": "Nenhum canal vinculado. A configuração inicial procurará um canal existente antes de criar."}
        try:
            channel = await linked_storage_channel(c, entry)
            return channel_info(channel)
        except HTTPException as exc:
            return {"ready": False, "state": "missing", "detail": exc.detail}
        except errors.FloodWaitError as exc:
            raise HTTPException(429, detail=f"O Telegram pediu uma pausa de {exc.seconds} segundos antes de verificar o canal.") from exc
        except (errors.RPCError, ConnectionError, TimeoutError, OSError) as exc:
            raise HTTPException(
                503, detail="Falha temporária ao verificar o canal no Telegram (" + type(exc).__name__ + "). "
                            "Sua conta não foi desconectada; tente novamente.",
            ) from exc


@app.post("/api/telegram/storage/ensure")
async def ensure_storage():
    async with lock:
        c, user_id = await authorized_account()
        links = channel_links()
        entry = links.get(user_id)
        try:
            if entry:
                entity = await linked_storage_channel(c, entry)
                await assign_drive_channel_logo(c, entity)
                return channel_info(entity)

            # First launch or recovery after a crash during channel creation:
            # look for exactly one owned channel BEFORE attempting CreateChannel.
            matches = await locate_storage_channels(c)
            if len(matches) == 1:
                channel = matches[0]
                links[user_id] = {"channel_id": str(channel.id)}
                save_channel_links(links)
                await assign_drive_channel_logo(c, channel)
                return {**channel_info(channel), "recovered": True}
            if len(matches) > 1:
                raise HTTPException(
                    409, detail="Há vários canais próprios chamados Drive Cloud Storage. "
                                "Para evitar duplicar seus arquivos, nenhum canal foi criado. "
                                "Verifique os canais no Telegram e escolha qual manter.",
                )

            result = await c(CreateChannelRequest(
                title=CHANNEL_TITLE, about=CHANNEL_MARKER, broadcast=True, megagroup=False,
            ))
            channel = next((item for item in result.chats if isinstance(item, Channel)), None)
            if channel is None:
                raise HTTPException(502, detail="O Telegram não confirmou o canal criado. "
                                               "Tente novamente: o Drive Cloud procurará um canal existente primeiro.")
            # Persist first: even if uploading a logo fails, the channel is safe.
            links[user_id] = {"channel_id": str(channel.id)}
            save_channel_links(links)
            avatar_applied = await assign_drive_channel_logo(c, channel)
            return {**channel_info(channel, created=True), "logo_applied": avatar_applied}
        except HTTPException:
            raise
        except errors.FloodWaitError as exc:
            raise HTTPException(429, detail=f"Limite temporário do Telegram. Tente novamente em {exc.seconds} segundos.") from exc
        except errors.RPCError as exc:
            raise HTTPException(
                502, detail="Telegram recusou a verificação ou criação do canal (" + type(exc).__name__ + "). "
                            "Confira sua conexão e permissões e tente novamente.",
            ) from exc
        except (ConnectionError, TimeoutError, OSError) as exc:
            raise HTTPException(
                503, detail="Conexão interrompida ao verificar o canal (" + type(exc).__name__ + "). "
                            "Sua conta e arquivos foram preservados. Tente novamente.",
            ) from exc
        except Exception as exc:
            # An internal error must have a visible, actionable classification;
            # do not expose credentials, session bytes, phone numbers or paths.
            raise HTTPException(
                500, detail="Falha inesperada ao preparar o canal (" + type(exc).__name__ + "). "
                            "Seu vínculo não foi apagado. Informe este tipo de erro ao suporte.",
            ) from exc


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
from folder_sync import build_folder_sync_router
from resumable_upload import build_resumable_router
from catalog_telegram import build_catalog_sync_router
from storage_api import build_router
from backup_api import build_backup_router, backup_scheduler
from share_api import build_share_router
app.include_router(build_router(authorized_account, channel_links, lock))
app.include_router(build_resumable_router(authorized_account, channel_links, lock))
from storage_api import connection, channel_id
app.include_router(build_catalog_sync_router(authorized_account, channel_links, lock, connection, channel_id))
folder_sync_router, folder_sync_scheduler = build_folder_sync_router(authorized_account, channel_links, lock)
app.include_router(folder_sync_router)
app.include_router(build_backup_router(authorized_account, channel_links, lock))
app.include_router(build_share_router(authorized_account, channel_links, lock))

@app.on_event("startup")
async def start_catalog_backup_scheduler():
    app.state.catalog_backup_task = asyncio.create_task(
        backup_scheduler(authorized_account, channel_links, lock)
    )
    app.state.folder_sync_task = asyncio.create_task(folder_sync_scheduler())

@app.on_event("shutdown")
async def stop_catalog_backup_scheduler():
    folder_task = getattr(app.state, "folder_sync_task", None)
    if folder_task:
        folder_task.cancel()
        try:
            await folder_task
        except asyncio.CancelledError:
            pass
    task = getattr(app.state, "catalog_backup_task", None)
    if task:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
