"""Local-only scheduled *catalog metadata* snapshots.

These JSON snapshots are not copies of Telegram file contents. For a file copy,
users must download a folder ZIP. All snapshots stay on this PC.
"""
import asyncio
import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Literal

from storage_api import connection, channel_id, DB_PATH

SNAPSHOT_DIR = DB_PATH.parent / "catalog_backups"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
try:
    SNAPSHOT_DIR.chmod(0o700)
except OSError:
    pass

INTERVALS = {"daily": 86400, "weekly": 604800}
KEEP_COUNT = 25

def schema(db):
    db.execute("""CREATE TABLE IF NOT EXISTS catalog_backup_schedule(
        account TEXT PRIMARY KEY,
        frequency TEXT NOT NULL DEFAULT 'off',
        next_run INTEGER
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS catalog_backup_history(
        id TEXT PRIMARY KEY,
        account TEXT NOT NULL,
        created INTEGER NOT NULL,
        item_count INTEGER NOT NULL,
        bytes INTEGER NOT NULL,
        source TEXT NOT NULL,
        filename TEXT NOT NULL
    )""")
    db.execute("CREATE INDEX IF NOT EXISTS catalog_backup_history_account ON catalog_backup_history(account,created)")

def snapshot(db, account, cid, source):
    """Called inside the caller's account lock; writes JSON atomically."""
    rows = db.execute("""SELECT id,kind,parent,name,size,mime,message_id,created,trashed,starred
        FROM nodes WHERE account=? ORDER BY created,id""",(account,)).fetchall()
    payload = {"format":"drive-cloud-catalog","version":1,
               "exported_at":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime()),
               "telegram_account":account,"channel_id":str(cid),
               "items":[dict(row) for row in rows]}
    backup_id = str(uuid.uuid4())
    filename = backup_id+".json"
    path = SNAPSHOT_DIR / filename
    tmp = SNAPSHOT_DIR / (filename+".tmp")
    raw = json.dumps(payload,ensure_ascii=False,indent=2).encode("utf-8")
    try:
        with tmp.open("xb") as f:
            os.chmod(tmp,0o600)
            f.write(raw)
        tmp.replace(path)
        db.execute("""INSERT INTO catalog_backup_history
            (id,account,created,item_count,bytes,source,filename)
            VALUES (?,?,?,?,?,?,?)""",
            (backup_id,account,int(time.time()),len(rows),len(raw),source,filename))
        outdated=db.execute("""SELECT id,filename FROM catalog_backup_history
            WHERE account=? ORDER BY created DESC LIMIT -1 OFFSET ?""",
            (account,KEEP_COUNT)).fetchall()
        for item in outdated:
            (SNAPSHOT_DIR/item["filename"]).unlink(missing_ok=True)
            db.execute("DELETE FROM catalog_backup_history WHERE id=? AND account=?",(item["id"],account))
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return {"id":backup_id,"created":int(time.time()),"item_count":len(rows),
            "bytes":len(raw),"source":source}

class ScheduleInput(BaseModel):
    frequency: Literal["off","daily","weekly"]

def build_backup_router(authorized_account, channel_links, lock):
    router = APIRouter(prefix="/api/backup")

    @router.get("/status")
    async def status():
        async with lock:
            _,account=await authorized_account()
            channel_id(channel_links,account)
            with connection() as db:
                schema(db)
                schedule=db.execute("SELECT frequency,next_run FROM catalog_backup_schedule WHERE account=?",(account,)).fetchone()
                latest=db.execute("""SELECT created,item_count FROM catalog_backup_history
                    WHERE account=? ORDER BY created DESC LIMIT 1""",(account,)).fetchone()
            return {"frequency":schedule["frequency"] if schedule else "off",
                    "next_run":schedule["next_run"] if schedule else None,
                    "last_backup":dict(latest) if latest else None,
                    "type":"catalog_metadata_only"}

    @router.post("/schedule")
    async def set_schedule(body: ScheduleInput):
        async with lock:
            _,account=await authorized_account()
            channel_id(channel_links,account)
            next_run=int(time.time())+INTERVALS[body.frequency] if body.frequency in INTERVALS else None
            with connection() as db:
                schema(db)
                db.execute("""INSERT INTO catalog_backup_schedule(account,frequency,next_run) VALUES (?,?,?)
                    ON CONFLICT(account) DO UPDATE SET frequency=excluded.frequency,next_run=excluded.next_run""",
                    (account,body.frequency,next_run))
            return {"frequency":body.frequency,"next_run":next_run}

    @router.post("/run")
    async def run():
        async with lock:
            _,account=await authorized_account()
            cid=channel_id(channel_links,account)
            with connection() as db:
                schema(db)
                result=snapshot(db,account,cid,"manual")
            return result

    @router.get("/history")
    async def history():
        async with lock:
            _,account=await authorized_account()
            channel_id(channel_links,account)
            with connection() as db:
                schema(db)
                rows=db.execute("""SELECT id,created,item_count,bytes,source
                    FROM catalog_backup_history WHERE account=? ORDER BY created DESC LIMIT 25""",(account,)).fetchall()
            return {"items":[dict(row) for row in rows]}

    @router.get("/history/{backup_id}/download")
    async def download(backup_id:str):
        try:
            uuid.UUID(backup_id)
        except ValueError:
            raise HTTPException(422,"Identificador inválido")
        async with lock:
            _,account=await authorized_account()
            channel_id(channel_links,account)
            with connection() as db:
                schema(db)
                row=db.execute("SELECT filename FROM catalog_backup_history WHERE id=? AND account=?",(backup_id,account)).fetchone()
            if not row:
                raise HTTPException(404,"Backup não encontrado")
            path=SNAPSHOT_DIR / row["filename"]
            if not path.exists():
                raise HTTPException(404,"Arquivo de backup não encontrado neste computador")
            return FileResponse(path,media_type="application/json",
                                filename="drive-cloud-catalog-"+backup_id[:8]+".json",
                                headers={"Cache-Control":"no-store"})
    return router

async def backup_scheduler(authorized_account, channel_links, lock):
    """Runs while the local backend is running. Does not run while PC is off."""
    while True:
        try:
            await asyncio.sleep(45)
            async with lock:
                _,account=await authorized_account()
                cid=channel_id(channel_links,account)
                now=int(time.time())
                with connection() as db:
                    schema(db)
                    schedule=db.execute("SELECT frequency,next_run FROM catalog_backup_schedule WHERE account=?",(account,)).fetchone()
                    if schedule and schedule["frequency"] in INTERVALS and schedule["next_run"] is not None and schedule["next_run"]<=now:
                        snapshot(db,account,cid,"scheduled")
                        db.execute("""UPDATE catalog_backup_schedule SET next_run=?
                            WHERE account=?""",(now+INTERVALS[schedule["frequency"]],account))
        except asyncio.CancelledError:
            raise
        except Exception:
            # A missing/offline Telegram session must not terminate the scheduler.
            continue
