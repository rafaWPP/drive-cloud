"""Safe, manual Telegram catalog snapshots.

This does not synchronize file contents or merge two concurrently modified catalogs.
The app uploads a versioned JSON snapshot to the user's own private storage channel.
Restore is intentionally download-only until conflict-aware reconciliation exists.
"""
import io
import json
import sqlite3
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

MARKER = "DRIVE_CLOUD_CATALOG_SNAPSHOT_V1"
MAX_SNAPSHOT_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 10000


def catalog_payload(db: sqlite3.Connection, account: str, channel: int) -> dict:
    rows = db.execute(
        "SELECT id,kind,parent,name,size,mime,message_id,created,trashed,starred "
        "FROM nodes WHERE account=? ORDER BY created,id", (account,)
    ).fetchall()
    if len(rows) > MAX_ITEMS:
        raise HTTPException(413, "Catálogo muito grande para um snapshot único.")
    return {
        "format": "drive-cloud-catalog",
        "version": 1,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "telegram_account": account,
        "channel_id": str(channel),
        "items": [dict(row) for row in rows],
    }


def encode_catalog(payload: dict) -> bytes:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(413, "Catálogo excede 2 MB. Nenhum snapshot foi enviado.")
    return raw


def decode_catalog(raw: bytes, account: str, channel: int) -> dict:
    if len(raw) > MAX_SNAPSHOT_BYTES:
        raise HTTPException(413, "Snapshot excede o limite de 2 MB.")
    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise HTTPException(422, "Snapshot inválido.") from exc
    if not isinstance(payload, dict) or payload.get("format") != "drive-cloud-catalog" or payload.get("version") != 1:
        raise HTTPException(422, "Formato do snapshot incompatível.")
    if payload.get("telegram_account") != account or str(payload.get("channel_id")) != str(channel):
        raise HTTPException(409, "Snapshot pertence a outra conta ou canal Telegram.")
    if not isinstance(payload.get("items"), list) or len(payload["items"]) > MAX_ITEMS:
        raise HTTPException(422, "Quantidade de itens inválida.")
    return payload


async def send_catalog_snapshot(client, db, account, channel):
    """Save metadata in the account's private channel without changing files."""
    raw = encode_catalog(catalog_payload(db, account, channel))
    file = io.BytesIO(raw)
    file.name = "drive-cloud-catalog-v1.json"
    try:
        message = await client.send_file(
            channel, file, caption=MARKER, force_document=True
        )
    except Exception as exc:
        raise HTTPException(502, "Não foi possível salvar o catálogo no Telegram.") from exc
    return {"saved": True, "message_id": message.id, "bytes": len(raw)}


def build_catalog_sync_router(authorized_account, channel_links, lock, connection, channel_id):
    router = APIRouter(prefix="/api/cloud/catalog/telegram")

    @router.post("/snapshot")
    async def upload_snapshot():
        async with lock:
            client, account = await authorized_account()
            channel = channel_id(channel_links, account)
            with connection() as db:
                return await send_catalog_snapshot(client, db, account, channel)

    async def newest_snapshot(client, channel):
        # Search only the private storage channel. Never assume other files are catalogs.
        async for message in client.iter_messages(channel, search=MARKER, limit=40):
            if message.message == MARKER and message.file:
                return message
        raise HTTPException(404, "Nenhum snapshot do catálogo encontrado neste canal.")

    @router.get("/latest")
    async def latest():
        async with lock:
            client, account = await authorized_account()
            channel = channel_id(channel_links, account)
            message = await newest_snapshot(client, channel)
            if not message.file.size or message.file.size > MAX_SNAPSHOT_BYTES:
                raise HTTPException(413, "Snapshot remoto excede o limite suportado.")
            raw = await client.download_media(message, file=bytes)
            if not isinstance(raw, bytes):
                raise HTTPException(502, "Falha ao recuperar snapshot no Telegram.")
            payload = decode_catalog(raw, account, channel)
            return {
                "available": True,
                "message_id": message.id,
                "items": len(payload["items"]),
                "exported_at": payload.get("exported_at"),
                "bytes": len(raw),
            }

    @router.get("/download")
    async def download():
        async with lock:
            client, account = await authorized_account()
            channel = channel_id(channel_links, account)
            message = await newest_snapshot(client, channel)
            if not message.file.size or message.file.size > MAX_SNAPSHOT_BYTES:
                raise HTTPException(413, "Snapshot remoto excede o limite suportado.")
            raw = await client.download_media(message, file=bytes)
            if not isinstance(raw, bytes):
                raise HTTPException(502, "Falha ao recuperar snapshot no Telegram.")
            decode_catalog(raw, account, channel)
            return Response(
                raw, media_type="application/json",
                headers={
                    "Content-Disposition": 'attachment; filename="drive-cloud-telegram-catalog.json"',
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )

    return router
