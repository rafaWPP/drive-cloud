"""Non-destructive archive of the previous channel's local metadata.

A Telegram message_id is scoped to a channel. When the user explicitly
replaces a missing channel, old catalog entries must not be shown as if they
were files in the new channel. We retain them in the same SQLite database,
under a read-only archive account scope; no old rows are deleted.
"""
import sqlite3
import time
import uuid


ACCOUNT_TABLES = (
    ("nodes", "account"),
    ("sync_folders", "account"),
    ("sync_catalog_seen", "account"),
    ("catalog_backup_schedule", "account"),
    ("catalog_backup_history", "account"),
    ("share_links", "owner"),
    ("resumable_uploads", "account"),
)


def archive_channel_metadata(db: sqlite3.Connection, account: str,
                             old_channel: str, new_channel: str) -> dict:
    if str(old_channel) == str(new_channel):
        raise ValueError("O novo canal não pode ser o mesmo canal anterior.")
    archive = f"archived:{account}:{old_channel}:{uuid.uuid4().hex}"
    db.execute("""CREATE TABLE IF NOT EXISTS drive_channel_archives (
        id TEXT PRIMARY KEY, original_account TEXT NOT NULL,
        archived_account TEXT NOT NULL UNIQUE, old_channel TEXT NOT NULL,
        new_channel TEXT NOT NULL, created INTEGER NOT NULL,
        node_count INTEGER NOT NULL, folder_sync_count INTEGER NOT NULL
    )""")
    present = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    nodes = 0
    sync_folders = 0
    if "nodes" in present:
        nodes = db.execute("SELECT COUNT(*) FROM nodes WHERE account=?", (account,)).fetchone()[0]
    if "sync_folders" in present:
        sync_folders = db.execute(
            "SELECT COUNT(*) FROM sync_folders WHERE account=?", (account,)
        ).fetchone()[0]

    # All moves and the archive entry are in the caller's SQLite transaction.
    # This also disables old background sync/schedules by moving their owner
    # scope away from the currently connected Telegram account.
    for table, column in ACCOUNT_TABLES:
        if table in present:
            db.execute(
                f"UPDATE {table} SET {column}=? WHERE {column}=?",
                (archive, account),
            )
    db.execute(
        """INSERT INTO drive_channel_archives
           (id,original_account,archived_account,old_channel,new_channel,
            created,node_count,folder_sync_count)
           VALUES (?,?,?,?,?,?,?,?)""",
        (str(uuid.uuid4()), account, archive, str(old_channel),
         str(new_channel), int(time.time()), nodes, sync_folders),
    )
    return {"archived_account": archive, "node_count": nodes,
            "folder_sync_count": sync_folders}


def existing_catalog_counts(db: sqlite3.Connection, account: str) -> dict:
    present = {row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    results = {"catalog_items": 0, "sync_folders": 0}
    if "nodes" in present:
        results["catalog_items"] = db.execute(
            "SELECT COUNT(*) FROM nodes WHERE account=?", (account,)
        ).fetchone()[0]
    if "sync_folders" in present:
        results["sync_folders"] = db.execute(
            "SELECT COUNT(*) FROM sync_folders WHERE account=?", (account,)
        ).fetchone()[0]
    return results
