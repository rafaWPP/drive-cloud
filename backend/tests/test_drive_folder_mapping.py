"""Folder pairs: local PC directory <-> an actual Meu Drive folder."""
import asyncio
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

import folder_sync
from folder_sync import (FolderRequest, ensure_schema, list_remote_folders,
                         new_remote_folder_name, remote_folder_path)


class DriveFolderMappingTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="dc-map-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "PcFotos"
        self.root.mkdir()
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.addCleanup(self.db.close)
        self.db.execute("""CREATE TABLE nodes (
            id TEXT PRIMARY KEY, account TEXT NOT NULL, parent TEXT, name TEXT,
            kind TEXT, size INTEGER NOT NULL DEFAULT 0, message_id INTEGER,
            created INTEGER, trashed INTEGER NOT NULL DEFAULT 0)""")
        ensure_schema(self.db)
        self.fotos = str(uuid.uuid4())
        self.ano = str(uuid.uuid4())
        self.insert_folder(self.fotos, "Fotos", None)
        self.insert_folder(self.ano, "2026", self.fotos)
        self.db.commit()
        self.patchers = [
            patch.object(folder_sync, "connection", new=lambda: self.db),
        ]
        for item in self.patchers:
            item.start()
            self.addCleanup(item.stop)
        self.router, _ = folder_sync.build_folder_sync_router(
            AsyncMock(return_value=(object(), "account")),
            lambda: {"account": {"channel_id": "333"}},
            asyncio.Lock(),
        )

    def insert_folder(self, identifier, name, parent=None, account="account", trashed=0):
        self.db.execute(
            "INSERT INTO nodes (id,account,parent,name,kind,created,trashed) "
            "VALUES (?,?,?,?,'folder',?,?)",
            (identifier, account, parent, name, 1, trashed),
        )

    def endpoint(self, path, method):
        matches = [
            route.endpoint for route in self.router.routes
            if route.path == path and method in route.methods
        ]
        self.assertEqual(len(matches), 1)
        return matches[0]

    def test_nested_real_drive_paths_are_shown(self):
        paths = list_remote_folders(self.db, "account")
        self.assertEqual(
            {r["path"] for r in paths}, {"Fotos", "Fotos / 2026"}
        )
        self.assertEqual(
            remote_folder_path(self.db, "account", self.ano), "Fotos / 2026"
        )

    def test_trashed_parent_never_exposes_nested_destination(self):
        self.db.execute("UPDATE nodes SET trashed=1 WHERE id=?", (self.fotos,))
        self.assertEqual(list_remote_folders(self.db, "account"), [])
        with self.assertRaises(HTTPException) as caught:
            remote_folder_path(self.db, "account", self.ano)
        self.assertEqual(caught.exception.status_code, 409)

    def test_account_isolation(self):
        hidden = str(uuid.uuid4())
        self.insert_folder(hidden, "Confidencial", None, account="other")
        self.assertNotIn("Confidencial", {item["name"] for item in
                                         list_remote_folders(self.db, "account")})
        with self.assertRaises(HTTPException):
            remote_folder_path(self.db, "account", hidden)

    def test_remote_parent_cycle_is_not_selectable(self):
        self.db.execute("UPDATE nodes SET parent=? WHERE id=?", (self.ano, self.fotos))
        with self.assertRaises(HTTPException):
            remote_folder_path(self.db, "account", self.ano)
        self.assertEqual(list_remote_folders(self.db, "account"), [])

    def test_invalid_new_drive_folder_names_are_rejected(self):
        for value in ("", "   ", ".", "..", "Photos/2026", "Photos\\2026", "file\x00name"):
            with self.subTest(value=value):
                with self.assertRaises(HTTPException):
                    new_remote_folder_name(value)

    async def test_can_link_pc_to_existing_nested_drive_folder(self):
        endpoint = self.endpoint("/api/sync/folders", "POST")
        created = await endpoint(FolderRequest(
            path=str(self.root), remote_root_id=self.ano, mode="two-way",
            automatic=True,
        ))
        self.assertEqual(created["remote_path"], "Fotos / 2026")
        self.assertEqual(created["mode"], "two-way")
        self.assertTrue(created["enabled"])
        rows = self.db.execute("SELECT * FROM sync_folders").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["root_node"], self.ano)
        self.assertEqual(rows[0]["mode"], "two-way")
        self.assertEqual(rows[0]["enabled"], 1)
        folders = await self.endpoint("/api/sync/folders", "GET")()
        self.assertEqual(folders["folders"][0]["remote_path"], "Fotos / 2026")

    async def test_link_new_drive_root_folder_without_creating_telegram_channel(self):
        result = await self.endpoint("/api/sync/folders", "POST")(FolderRequest(
            path=str(self.root), remote_folder_name="Projetos",
        ))
        self.assertEqual(result["remote_path"], "Projetos")
        self.assertEqual(
            self.db.execute("SELECT name FROM nodes WHERE id=?", (
                self.db.execute("SELECT root_node FROM sync_folders").fetchone()[0],
            )).fetchone()[0], "Projetos"
        )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 3)

    async def test_same_drive_folder_cannot_map_two_local_folders(self):
        endpoint = self.endpoint("/api/sync/folders", "POST")
        await endpoint(FolderRequest(path=str(self.root), remote_root_id=self.fotos))
        another = Path(self.temp.name) / "Another"
        another.mkdir()
        with self.assertRaises(HTTPException) as caught:
            await endpoint(FolderRequest(path=str(another), remote_root_id=self.fotos))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sync_folders").fetchone()[0], 1)

    async def test_rejects_nonexistent_folder_without_creating_anything(self):
        with self.assertRaises(HTTPException):
            await self.endpoint("/api/sync/folders", "POST")(FolderRequest(
                path=str(self.root), remote_root_id=str(uuid.uuid4()),
            ))
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sync_folders").fetchone()[0], 0)

    async def test_same_new_folder_name_must_select_existing_instead(self):
        with self.assertRaises(HTTPException) as caught:
            await self.endpoint("/api/sync/folders", "POST")(FolderRequest(
                path=str(self.root), remote_folder_name="Fotos",
            ))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM sync_folders").fetchone()[0], 0)

    async def test_existing_mapped_drive_destination_is_marked_in_picker(self):
        await self.endpoint("/api/sync/folders", "POST")(FolderRequest(
            path=str(self.root), remote_root_id=self.fotos,
        ))
        result = await self.endpoint("/api/sync/remote-folders", "GET")()
        marked = next(row for row in result["folders"] if row["id"] == self.fotos)
        self.assertEqual(marked["linked_local_path"], str(self.root))


if __name__ == "__main__":
    unittest.main()
