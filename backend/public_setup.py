"""Optional Cloudflare connector setup for desktop only.

This module never publishes the private Drive Cloud API or starts a tunnel.
The public file gateway is intentionally a separate prerequisite.
"""
import hashlib
import json
import os
import platform
import re
import shutil
import stat
import threading
import time
import urllib.request
from pathlib import Path

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/public-setup")
_lock = threading.Lock()
_job = {"stage": "idle", "percent": 0, "detail": "", "error": ""}
_in_progress = False

def _data():
    root = Path(os.environ.get("DRIVE_CLOUD_DATA_DIR") or Path(__file__).resolve().parent / ".data")
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root

def _asset():
    if platform.machine().lower() not in ("x86_64", "amd64"):
        raise RuntimeError("Instalação automática disponível apenas em sistemas x64.")
    if os.name == "nt":
        return "cloudflared-windows-amd64.exe"
    if platform.system() == "Linux":
        return "cloudflared-linux-amd64"
    raise RuntimeError("Sistema operacional ainda não suportado.")

def _target():
    return _data() / "public-sharing" / _asset()

def _progress(stage, percent, detail, error=""):
    with _lock:
        _job.update(stage=stage, percent=percent, detail=detail, error=error)

def _worker():
    global _in_progress
    staging = None
    try:
        name = _asset()
        _progress("release", 2, "Consultando versão oficial da Cloudflare...")
        api = urllib.request.Request(
            "https://api.github.com/repos/cloudflare/cloudflared/releases/latest",
            headers={"User-Agent": "DriveCloud-desktop", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(api, timeout=30) as response:
            release = json.load(response)
        asset = next((a for a in release.get("assets", []) if a.get("name") == name), None)
        if not asset:
            raise RuntimeError("Não foi encontrado um conector oficial para este sistema.")
        digest = asset.get("digest", "")
        if not re.fullmatch(r"sha256:[a-fA-F0-9]{64}", digest):
            raise RuntimeError("O GitHub não forneceu SHA-256 verificável para este pacote. Instalação cancelada.")
        url = asset.get("browser_download_url", "")
        if not url.startswith("https://github.com/cloudflare/cloudflared/releases/download/"):
            raise RuntimeError("Origem do pacote não corresponde ao repositório oficial.")
        expected = digest.split(":", 1)[1].lower()
        size = int(asset.get("size") or 0)
        if size <= 0 or size > 150 * 1024 * 1024:
            raise RuntimeError("Tamanho do pacote inválido.")
        dest = _target()
        dest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        staging = dest.with_name(dest.name + ".download")
        written = 0
        sha = hashlib.sha256()
        request = urllib.request.Request(url, headers={"User-Agent": "DriveCloud-desktop"})
        _progress("download", 5, "Baixando conector oficial...")
        with urllib.request.urlopen(request, timeout=90) as response, staging.open("wb") as output:
            while True:
                block = response.read(256 * 1024)
                if not block:
                    break
                written += len(block)
                if written > 150 * 1024 * 1024:
                    raise RuntimeError("Download ultrapassou o limite de segurança.")
                output.write(block)
                sha.update(block)
                _progress("download", min(90, 5 + int(85 * written / size)),
                          f"Baixando: {written // 1048576} de {size // 1048576} MiB")
        _progress("verify", 93, "Verificando integridade SHA-256...")
        if written != size or sha.hexdigest() != expected:
            raise RuntimeError("Integridade do download não conferiu. Arquivo descartado.")
        if os.name != "nt":
            staging.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR)
        os.replace(staging, dest)
        _progress("complete", 100, "Conector instalado. Nenhum serviço público foi iniciado.")
    except Exception as exc:
        _progress("error", 0, "Falha na instalação.", str(exc))
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
        with _lock:
            _in_progress = False

@router.get("/status")
def status():
    try:
        target = _target()
        installed = target.is_file()
        system = platform.system()
        supported = system in ("Linux", "Windows") and platform.machine().lower() in ("x86_64", "amd64")
    except RuntimeError:
        installed = False
        supported = False
        system = platform.system()
    with _lock:
        job = dict(_job)
    return {
        "supported": supported, "system": system, "installed": installed,
        "installation": job,
        "public_gateway_ready": False,
        "sharing_enabled": False,
        "local_service_url": None,
        "message": "Compartilhamento público ainda não disponível. O backend privado nunca deve ser exposto."
    }

@router.post("/install")
def install():
    global _in_progress
    try:
        target = _target()
    except RuntimeError as exc:
        raise HTTPException(422, str(exc))
    with _lock:
        if _in_progress:
            raise HTTPException(409, "Instalação já em andamento.")
        if target.is_file():
            return {"started": False, "installed": True}
        _in_progress = True
        _job.update(stage="starting", percent=1, detail="Iniciando instalação opcional...", error="")
    threading.Thread(target=_worker, name="drive-cloud-cloudflared-install", daemon=True).start()
    return {"started": True, "installed": False}
