"""Regression tests for Telegram storage onboarding after app restarts.

All Telegram operations are mocked: no account or real channel is contacted.
"""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from telethon.tl.functions.channels import CreateChannelRequest

import server


class FakeChannel:
    def __init__(self, channel_id, title="Drive Cloud Storage", creator=True, broadcast=True):
        self.id = channel_id
        self.title = title
        self.creator = creator
        self.broadcast = broadcast
        self.photo = object()
        self.username = None
        self.usernames = []


class FakeTelegramClient:
    def __init__(self, dialogs=(), cache_missing=False, error=None):
        self.dialogs = list(dialogs)
        self.cache_missing = cache_missing
        self.error = error
        self.created = 0
        self.looked_up = 0
        self.scanned = 0

    async def get_entity(self, identifier):
        self.looked_up += 1
        if self.cache_missing:
            raise ValueError("Could not find the input entity for channel")
        for channel in self.dialogs:
            if channel.id == identifier:
                return channel
        raise ValueError("No such entity")

    async def iter_dialogs(self):
        self.scanned += 1
        if self.error is not None:
            raise self.error
        for channel in self.dialogs:
            yield SimpleNamespace(entity=channel)

    async def __call__(self, request):
        if not isinstance(request, CreateChannelRequest):
            raise AssertionError("Unexpected Telegram operation")
        self.created += 1
        channel = FakeChannel(500 + self.created)
        self.dialogs.append(channel)
        return SimpleNamespace(chats=[channel])


class StorageRecoveryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.links = {}
        self.saved = []
        self.client = FakeTelegramClient()
        self.patches = [
            patch.object(server, "Channel", FakeChannel),
            patch.object(server, "lock", asyncio.Lock()),
            patch.object(server, "authorized_account", new=AsyncMock(side_effect=self.account)),
            patch.object(server, "channel_links", new=lambda: self.links),
            patch.object(server, "save_channel_links", new=lambda links: self.saved.append(dict(links))),
            patch.object(server, "assign_drive_channel_logo", new=AsyncMock(return_value=True)),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    async def account(self):
        return self.client, "123"

    async def test_reuses_existing_own_channel_before_create(self):
        channel = FakeChannel(222)
        self.client.dialogs = [channel]
        result = await server.ensure_storage()
        self.assertTrue(result["ready"])
        self.assertTrue(result["recovered"])
        self.assertEqual(result["channel_id"], "222")
        self.assertEqual(self.client.created, 0)
        self.assertEqual(self.saved[-1]["123"]["channel_id"], "222")

    async def test_linked_channel_is_recovered_after_telethon_cache_loss(self):
        self.client.dialogs = [FakeChannel(345)]
        self.client.cache_missing = True
        self.links["123"] = {"channel_id": "345"}
        status = await server.storage_status()
        self.assertTrue(status["ready"])
        self.assertEqual(status["channel_id"], "345")
        result = await server.ensure_storage()
        self.assertEqual(result["channel_id"], "345")
        self.assertEqual(self.client.created, 0)
        self.assertEqual(self.saved, [])

    async def test_creates_channel_only_if_absent_and_does_not_duplicate_on_retry(self):
        first = await server.ensure_storage()
        self.assertTrue(first["created"])
        self.assertTrue(first["logo_applied"])
        self.assertEqual(self.client.created, 1)
        second = await server.ensure_storage()
        self.assertEqual(second["channel_id"], first["channel_id"])
        self.assertEqual(self.client.created, 1)

    async def test_missing_recorded_channel_never_creates_another(self):
        self.links["123"] = {"channel_id": "999"}
        self.client.cache_missing = True
        with self.assertRaises(HTTPException) as caught:
            await server.ensure_storage()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("Nenhum canal será criado", caught.exception.detail)
        self.assertEqual(self.client.created, 0)

    async def test_multiple_owned_channels_stops_before_creation(self):
        self.client.dialogs = [FakeChannel(10), FakeChannel(11)]
        with self.assertRaises(HTTPException) as caught:
            await server.ensure_storage()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.client.created, 0)
        self.assertEqual(self.saved, [])

    async def test_public_channel_is_never_used_as_private_storage(self):
        public = FakeChannel(675)
        public.username = "drive_cloud_public"
        self.client.dialogs = [public]
        with self.assertRaises(HTTPException) as caught:
            await server.ensure_storage()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("público", caught.exception.detail)
        self.assertEqual(self.client.created, 0)
        self.assertEqual(self.saved, [])

    async def test_linked_channel_becoming_public_is_blocked(self):
        public = FakeChannel(345)
        public.username = "public_backup"
        self.links["123"] = {"channel_id": "345"}
        self.client.dialogs = [public]
        with self.assertRaises(HTTPException) as caught:
            await server.ensure_storage()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertIn("público", caught.exception.detail)
        self.assertEqual(self.client.created, 0)

    async def test_unexpected_telegram_lookup_failure_is_visible(self):
        self.client.error = RuntimeError("Fake internal Telegram failure")
        with self.assertRaises(HTTPException) as caught:
            await server.ensure_storage()
        self.assertEqual(caught.exception.status_code, 500)
        self.assertIn("RuntimeError", caught.exception.detail)
        self.assertNotIn("Fake internal Telegram failure", caught.exception.detail)

    async def test_unauthorized_link_not_silently_replaced(self):
        self.links["123"] = {"channel_id": "345"}
        self.client.dialogs = [FakeChannel(345, broadcast=False)]
        with self.assertRaises(HTTPException) as caught:
            await server.ensure_storage()
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(self.client.created, 0)


if __name__ == "__main__":
    unittest.main()
