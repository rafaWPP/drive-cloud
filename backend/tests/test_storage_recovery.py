"""Safe deleted-channel recovery tests. No real Telegram account is used."""
import asyncio
import sqlite3
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from telethon.tl.functions.channels import CreateChannelRequest

import server
from server import RecoverStorageRequest
from storage_recovery import archive_channel_metadata, existing_catalog_counts


def fixture_db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE nodes (id TEXT PRIMARY KEY, account TEXT, kind TEXT, message_id INTEGER)")
    db.execute("CREATE TABLE sync_folders (id TEXT PRIMARY KEY, account TEXT)")
    db.execute("CREATE TABLE share_links (id TEXT PRIMARY KEY, owner TEXT)")
    db.execute("CREATE TABLE catalog_backup_schedule (account TEXT PRIMARY KEY)")
    db.execute("INSERT INTO nodes VALUES ('a','123','file',42)")
    db.execute("INSERT INTO sync_folders VALUES ('b','123')")
    db.execute("INSERT INTO share_links VALUES ('c','123')")
    db.execute("INSERT INTO catalog_backup_schedule VALUES ('123')")
    db.commit()
    return db


class MetadataArchiveTests(unittest.TestCase):
    def setUp(self):
        self.db = fixture_db()

    def tearDown(self):
        self.db.close()

    def test_replacement_archives_all_catalog_records_without_deleting(self):
        with self.db:
            archived = archive_channel_metadata(self.db, "123", "999", "500")
        self.assertEqual(archived["node_count"], 1)
        self.assertEqual(archived["folder_sync_count"], 1)
        self.assertEqual(existing_catalog_counts(self.db, "123")["catalog_items"], 0)
        archived_scope = archived["archived_account"]
        self.assertEqual(
            self.db.execute("SELECT account FROM nodes WHERE id='a'").fetchone()[0],
            archived_scope
        )
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 1)
        self.assertEqual(
            self.db.execute("SELECT account FROM sync_folders WHERE id='b'").fetchone()[0],
            archived_scope,
        )
        self.assertEqual(
            self.db.execute("SELECT owner FROM share_links WHERE id='c'").fetchone()[0],
            archived_scope,
        )
        self.assertEqual(
            self.db.execute("SELECT COUNT(*) FROM drive_channel_archives").fetchone()[0], 1
        )

    def test_archive_transaction_rollback_preserves_active_metadata(self):
        with self.assertRaises(RuntimeError):
            with self.db:
                archive_channel_metadata(self.db, "123", "999", "500")
                raise RuntimeError("deliberate interruption")
        self.assertEqual(existing_catalog_counts(self.db, "123")["catalog_items"], 1)
        self.assertEqual(self.db.execute(
            "SELECT COUNT(*) FROM drive_channel_archives"
        ).fetchone()[0], 0)

    def test_replacing_same_channel_is_rejected(self):
        with self.assertRaises(ValueError):
            archive_channel_metadata(self.db, "123", "999", "999")


class FakeChannel:
    def __init__(self, channel_id, title="Drive Cloud Storage"):
        self.id = channel_id
        self.title = title
        self.broadcast = True
        self.creator = True
        self.photo = object()
        self.username = None
        self.usernames = []


class FakeClient:
    def __init__(self):
        self.dialogs = []
        self.created = 0

    async def get_entity(self, channel_id):
        for entry in self.dialogs:
            if entry.id == channel_id:
                return entry
        raise ValueError("input entity not in session")

    async def iter_dialogs(self):
        for item in self.dialogs:
            yield SimpleNamespace(entity=item)

    async def __call__(self, request):
        if not isinstance(request, CreateChannelRequest):
            raise AssertionError("Unexpected Telegram request")
        self.created += 1
        channel = FakeChannel(500 + self.created)
        self.dialogs.append(channel)
        return SimpleNamespace(chats=[channel])


class RecoveryEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = fixture_db()
        self.addCleanup(self.db.close)
        self.client = FakeClient()
        self.links = {"123": {"channel_id": "999"}}
        self.saved = []
        patches = [
            patch.object(server, "Channel", FakeChannel),
            patch.object(server, "lock", asyncio.Lock()),
            patch.object(server, "authorized_account", new=AsyncMock(
                return_value=(self.client, "123")
            )),
            patch.object(server, "channel_links", new=lambda: self.links),
            patch.object(server, "save_channel_links", new=self.save_links),
            patch.object(server, "connection", new=lambda: self.db),
            patch.object(server, "assign_drive_channel_logo", new=AsyncMock(
                return_value=True
            )),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def save_links(self, links):
        self.saved.append({k: dict(v) for k, v in links.items()})

    async def test_missing_channel_offers_new_channel_and_explains_catalog(self):
        options = await server.recovery_options()
        self.assertTrue(options["eligible"])
        self.assertEqual(options["expected_channel_id"], "999")
        self.assertEqual(options["catalog_items"], 1)
        self.assertEqual(options["sync_folders"], 1)
        self.assertEqual(options["candidates"], [])
        self.assertEqual(self.client.created, 0)

    async def test_user_confirmation_is_required(self):
        with self.assertRaises(HTTPException) as caught:
            await server.recover_storage(RecoverStorageRequest(
                action="create", expected_channel_id="999", confirmed=False
            ))
        self.assertEqual(caught.exception.status_code, 422)
        self.assertEqual(self.client.created, 0)

    async def test_explicit_create_archives_catalog_and_changes_link(self):
        result = await server.recover_storage(RecoverStorageRequest(
            action="create", expected_channel_id="999", confirmed=True
        ))
        self.assertTrue(result["ready"])
        self.assertTrue(result["created"])
        self.assertEqual(result["previous_catalog_archived"], 1)
        self.assertEqual(self.client.created, 1)
        self.assertEqual(self.links["123"]["channel_id"], "501")
        self.assertEqual(self.links["123"]["previous_channels"][0]["channel_id"], "999")
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 1)
        self.assertEqual(existing_catalog_counts(self.db, "123")["catalog_items"], 0)
        again = await server.ensure_storage()
        self.assertEqual(again["channel_id"], "501")
        self.assertEqual(self.client.created, 1)

    async def test_other_existing_channel_is_preferred_over_duplicate(self):
        self.client.dialogs = [FakeChannel(321)]
        options = await server.recovery_options()
        self.assertEqual(options["candidates"][0]["channel_id"], "321")
        with self.assertRaises(HTTPException) as caught:
            await server.recover_storage(RecoverStorageRequest(
                action="create", expected_channel_id="999", confirmed=True
            ))
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.client.created, 0)
        result = await server.recover_storage(RecoverStorageRequest(
            action="link", expected_channel_id="999", channel_id="321",
            confirmed=True
        ))
        self.assertEqual(result["channel_id"], "321")
        self.assertFalse(result["created"])
        self.assertEqual(self.client.created, 0)

    async def test_changed_link_rejected_without_side_effects(self):
        with self.assertRaises(HTTPException):
            await server.recover_storage(RecoverStorageRequest(
                action="create", expected_channel_id="111", confirmed=True
            ))
        self.assertEqual(self.links["123"]["channel_id"], "999")
        self.assertEqual(self.client.created, 0)
        self.assertEqual(existing_catalog_counts(self.db, "123")["catalog_items"], 1)

    async def test_reachable_old_channel_cannot_be_replaced(self):
        self.client.dialogs = [FakeChannel(999)]
        with self.assertRaises(HTTPException) as caught:
            await server.recovery_options()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.client.created, 0)


if __name__ == "__main__":
    unittest.main()
