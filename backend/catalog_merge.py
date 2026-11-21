"""Add-only, account-bound merge of portable Drive Cloud catalogs.

Never overwrites local metadata, deletes files, or accepts a different account
or channel. Snapshot history must be read in order, not only the newest one.
"""
import uuid
from fastapi import HTTPException

MAX_ITEMS = 10000


def merge_catalog(db, payload, account, channel, *, dry_run=False):
    if not isinstance(payload, dict) or payload.get("format") != "drive-cloud-catalog" or payload.get("version") != 1:
        raise HTTPException(422, "Formato do catálogo não suportado.")
    if payload.get("telegram_account") != account or str(payload.get("channel_id")) != str(channel):
        raise HTTPException(409, "O catálogo pertence a outra conta ou canal Telegram.")
    entries = payload.get("items")
    if not isinstance(entries, list) or len(entries) > MAX_ITEMS:
        raise HTTPException(422, "O catálogo remoto possui uma lista de itens inválida.")
    valid = []
    seen = set()
    for item in entries:
        if not isinstance(item, dict):
            raise HTTPException(422, "Registro inválido no catálogo remoto.")
        try:
            node_id = str(uuid.UUID(item["id"]))
            kind = item["kind"]
            parent = item.get("parent")
            parent = str(uuid.UUID(parent)) if parent is not None else None
            name = item["name"]
            size = item["size"]
            mime = item["mime"]
            message = item.get("message_id")
            created = item["created"]
            trashed = item.get("trashed", 0)
            starred = item.get("starred", 0)
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise HTTPException(422, "Metadados inválidos no catálogo remoto.") from exc
        if (node_id in seen or kind not in ("file", "folder")
                or not isinstance(name, str) or not name.strip() or len(name) > 180
                or not isinstance(size, int) or isinstance(size, bool) or size < 0
                or not isinstance(mime, str) or len(mime) > 160
                or not isinstance(created, int) or isinstance(created, bool) or created < 0
                or trashed not in (0, 1, False, True)
                or starred not in (0, 1, False, True)
                or (kind == "file" and (not isinstance(message, int) or isinstance(message, bool) or message <= 0))
                or (kind == "folder" and message is not None)):
            raise HTTPException(422, "Registro remoto inconsistente.")
        seen.add(node_id)
        valid.append((node_id, account, kind, parent, name, size, mime,
                      message, created, int(trashed), int(starred)))

    mapped = {r[0]: r for r in valid}
    existing_rows = db.execute("SELECT id,account,kind,parent,name,message_id FROM nodes").fetchall()
    existing = {row["id"]: row for row in existing_rows}
    for row in valid:
        identifier, _, kind, parent = row[:4]
        known = existing.get(identifier)
        if known and (known["account"] != account or known["kind"] != kind):
            raise HTTPException(409, "Identificador remoto incompatível com o catálogo local.")
        if parent is not None and parent not in mapped:
            parent_row = existing.get(parent)
            if not parent_row or parent_row["kind"] != "folder" or parent_row["account"] != account:
                raise HTTPException(422, "O catálogo remoto possui referência a pasta inexistente.")
        # Check cycles in the snapshot graph before any insertion.
        cursor = parent
        ancestors = {identifier}
        while cursor in mapped:
            if cursor in ancestors or mapped[cursor][2] != "folder":
                raise HTTPException(422, "Estrutura de pastas remota inválida.")
            ancestors.add(cursor)
            cursor = mapped[cursor][3]

    missing = [r for r in valid if r[0] not in existing]
    differences = sum(
        1 for r in valid if r[0] in existing
        and (existing[r[0]]["parent"] != r[3] or existing[r[0]]["name"] != r[4]
             or existing[r[0]]["message_id"] != r[7])
    )
    if missing and not dry_run:
        db.executemany(
            "INSERT INTO nodes "
            "(id,account,kind,parent,name,size,mime,message_id,created,trashed,starred) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)", missing,
        )
    return {"checked": len(valid), "imported": 0 if dry_run else len(missing),
            "new_items": len(missing), "metadata_differences_preserved": differences,
            "dry_run": dry_run}
