"""Drive Cloud multipart Telegram file format (v1).

One logical Drive file is represented by N ordinary Telegram documents and a
small manifest Telegram document. The catalog points to the manifest message.
Legacy single-document files remain readable without migration.

Transfers stage one part at a time on private local disk; never hold GB in RAM.
Do not delete earlier uploaded chunks after an uncertain send: they are orphaned
but may be recoverable, and deleting could destroy user data.
"""
import hashlib
import io
import json
import math
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import HTTPException
from telethon.tl.types import DocumentAttributeFilename

from telegram_limits import upload_limit

MANIFEST_MARKER = "DRIVE_CLOUD_MULTIPART_MANIFEST_V1"
PART_BYTES = 1024 * 1024 * 1024
MAX_FILE_BYTES = 20 * 1024 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
READ_BYTES = 1024 * 1024


def digest_file(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(READ_BYTES), b""):
            value.update(block)
    return value.hexdigest()


async def send_document(client, channel, path, name, mime, *, progress=None):
    """Upload a source file; multipart above Telegram's per-document limit."""
    source = Path(path)
    st = source.stat()
    if not source.is_file() or source.is_symlink() or st.st_size > MAX_FILE_BYTES:
        raise HTTPException(413, "Arquivo não suportado. Limite inicial: 20 GB por arquivo.")
    limit = await upload_limit(client)
    if st.st_size <= limit:
        message = await client.send_file(
            channel, str(source), force_document=True,
            part_size_kb=512, mime_type=mime,
            attributes=[DocumentAttributeFilename(name)],
            progress_callback=progress,
            caption="Drive Cloud • arquivo",
        )
        return message
    count = math.ceil(st.st_size / PART_BYTES)
    if count > 20:
        raise HTTPException(413, "Arquivo acima do limite inicial de 20 GB.")
    upload_id = str(uuid.uuid4())
    chunks = []
    sent_total = 0
    all_hash = hashlib.sha256()
    with source.open("rb") as input_file:
        for index in range(count):
            expected = min(PART_BYTES, st.st_size - sent_total)
            with tempfile.TemporaryDirectory(prefix=".dc-part-") as tmp:
                part = Path(tmp) / ("drive-cloud-part-" + upload_id + "-" + str(index + 1) + ".bin")
                digest = hashlib.sha256()
                remaining = expected
                with part.open("xb") as output:
                    os.chmod(part, 0o600)
                    while remaining:
                        block = input_file.read(min(READ_BYTES, remaining))
                        if not block:
                            raise HTTPException(409, "Arquivo de origem alterado durante o backup.")
                        digest.update(block)
                        all_hash.update(block)
                        output.write(block)
                        remaining -= len(block)
                # Each part is a separate normal Telegram document. Report
                # total logical progress, not progress of just the current part.
                base = sent_total
                def report(current, total, base=base):
                    if progress:
                        progress(base + current, st.st_size)
                chunk_msg = await client.send_file(
                    channel, str(part), force_document=True,
                    caption="Drive Cloud • parte " + str(index + 1) + "/" + str(count) + " • " + upload_id,
                    part_size_kb=512, progress_callback=report,
                )
                chunks.append({"message_id": chunk_msg.id, "size": expected, "sha256": digest.hexdigest()})
                sent_total += expected
    if source.stat().st_size != st.st_size or source.stat().st_mtime_ns != st.st_mtime_ns:
        raise HTTPException(409, "Arquivo de origem mudou durante o envio; partes preservadas no Telegram.")
    manifest = {
        "format": "drive-cloud-multipart", "version": 1,
        "upload_id": upload_id, "name": name, "size": st.st_size,
        "sha256": all_hash.hexdigest(), "parts": chunks,
    }
    raw = json.dumps(manifest, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if len(raw) > MAX_MANIFEST_BYTES:
        raise HTTPException(413, "Manifesto maior que o limite suportado.")
    data = io.BytesIO(raw)
    data.name = "drive-cloud-multipart-" + upload_id + ".json"
    marker = await client.send_file(channel, data, caption=MANIFEST_MARKER, force_document=True)
    if progress:
        progress(st.st_size, st.st_size)
    return marker


def parse_manifest(raw, expected_size):
    if not isinstance(raw, bytes) or len(raw) > MAX_MANIFEST_BYTES:
        raise HTTPException(502, "Manifesto do arquivo ausente ou muito grande.")
    try:
        payload = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise HTTPException(502, "Manifesto do arquivo corrompido.") from exc
    if not isinstance(payload, dict) or payload.get("format") != "drive-cloud-multipart" or payload.get("version") != 1:
        raise HTTPException(502, "Formato multipart incompatível.")
    parts = payload.get("parts")
    expected = payload.get("size")
    if (not isinstance(expected, int) or isinstance(expected, bool) or expected != expected_size or
        not 0 < expected <= MAX_FILE_BYTES or
        not isinstance(parts, list) or not 2 <= len(parts) <= 20):
        raise HTTPException(502, "Tamanho ou partes inválidas no manifesto.")
    if sum(p.get("size", -1) for p in parts if isinstance(p, dict)) != expected:
        raise HTTPException(502, "Tamanho das partes não confere com o arquivo.")
    for part in parts:
        if (not isinstance(part, dict) or
            not isinstance(part.get("message_id"), int) or isinstance(part["message_id"], bool) or part["message_id"] <= 0 or
            not isinstance(part.get("size"), int) or isinstance(part["size"], bool) or not 0 < part["size"] <= PART_BYTES or
            not isinstance(part.get("sha256"), str) or len(part["sha256"]) != 64 or
            any(c not in "0123456789abcdef" for c in part["sha256"])):
            raise HTTPException(502, "Referência de parte inválida.")
    if len({p["message_id"] for p in parts}) != len(parts):
        raise HTTPException(502, "Partes duplicadas no manifesto.")
    if (not isinstance(payload.get("sha256"), str) or
        len(payload["sha256"]) != 64 or
        any(c not in "0123456789abcdef" for c in payload["sha256"])):
        raise HTTPException(502, "Hash do arquivo inválido.")
    return payload


async def download_document(client, channel, message_id, size, output_path):
    """Download and verify a legacy or multipart Telegram document to disk."""
    message = await client.get_messages(channel, ids=message_id)
    if not message or not message.media:
        raise HTTPException(404, "Arquivo ou manifesto indisponível no Telegram.")
    destination = Path(output_path)
    if message.message != MANIFEST_MARKER:
        if getattr(message.file, "size", None) != size:
            raise HTTPException(502, "Tamanho remoto diferente do catálogo.")
        with destination.open("wb") as output:
            await client.download_media(message, file=output)
        if destination.stat().st_size != size:
            raise HTTPException(502, "Download incompleto.")
        return
    if getattr(message.file, "size", 0) > MAX_MANIFEST_BYTES:
        raise HTTPException(502, "Manifesto remoto excede o limite.")
    manifest = parse_manifest(await client.download_media(message, file=bytes), size)
    whole = hashlib.sha256()
    with destination.open("wb") as output:
        for part in manifest["parts"]:
            chunk = await client.get_messages(channel, ids=part["message_id"])
            if not chunk or not chunk.media or getattr(chunk.file, "size", None) != part["size"]:
                raise HTTPException(502, "Parte do arquivo ausente ou com tamanho incorreto no Telegram.")
            digest = hashlib.sha256()
            received = 0
            # Telethon downloads to a file-like target; it does not need to
            # stage every part in RAM or allocate a second full-size file.
            class CheckedOutput:
                def write(self, block):
                    nonlocal received
                    received += len(block)
                    if received > part["size"]:
                        raise HTTPException(502, "Parte maior que o tamanho esperado.")
                    digest.update(block)
                    whole.update(block)
                    return output.write(block)
                def flush(self):
                    return output.flush()
                def seek(self, *args):
                    return output.seek(*args)
                def tell(self):
                    return output.tell()
            await client.download_media(chunk, file=CheckedOutput())
            if received != part["size"] or digest.hexdigest() != part["sha256"]:
                raise HTTPException(502, "Uma parte do arquivo falhou na verificação SHA-256.")
        output.flush()
        os.fsync(output.fileno())
    if destination.stat().st_size != size or whole.hexdigest() != manifest["sha256"]:
        raise HTTPException(502, "Arquivo reconstruído não passou na verificação de integridade.")
