"""Regression coverage for multi-document Telegram backups.

Uses an in-memory Telegram client and tiny parts; no network or credentials.
Run with: python -m unittest discover -s backend/tests -p test_multipart_telegram.py
"""
import asyncio
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import multipart_telegram as multipart


class FakeTelegram:
    def __init__(self):
        self.messages = {}
        self.next_id = 1

    async def send_file(self, channel, file, *, caption=None, progress_callback=None, **kwargs):
        if isinstance(file, (str, Path)):
            data = Path(file).read_bytes()
        else:
            data = file.read()
        msg = SimpleNamespace(id=self.next_id, message=caption, media=True,
                              file=SimpleNamespace(size=len(data)), data=data)
        self.messages[msg.id] = msg
        self.next_id += 1
        if progress_callback:
            progress_callback(len(data), len(data))
        return msg

    async def get_messages(self, channel, ids):
        return self.messages.get(ids)

    async def download_media(self, message, file):
        if file is bytes:
            return message.data
        file.write(message.data)
        return file


async def tiny_limit(client):
    return 12


class MultipartTests(unittest.IsolatedAsyncioTestCase):
    async def test_split_reconstruct_and_hash(self):
        client = FakeTelegram()
        content = b"abcdefghijklmnopqrstuvwxyz" * 2
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / "original.bin"
            recovered = Path(folder) / "recovered.bin"
            original.write_bytes(content)
            with patch.object(multipart, "PART_BYTES", 8), patch.object(multipart, "upload_limit", tiny_limit):
                msg = await multipart.send_document(client, 123, original, "original.bin",
                                                    "application/octet-stream")
                self.assertTrue(msg.message.startswith(multipart.MANIFEST_MARKER))
                self.assertEqual(len(client.messages), 8)  # 7 chunks + 1 manifest
                manifest = multipart.parse_manifest(msg.data, len(content))
                self.assertEqual(len(manifest["parts"]), 7)
                await multipart.download_document(client, 123, msg.id, len(content), recovered)
            self.assertEqual(recovered.read_bytes(), content)

    async def test_corrupted_part_is_rejected(self):
        client = FakeTelegram()
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / "source.bin"
            recovered = Path(folder) / "out.bin"
            original.write_bytes(b"correct content over limit")
            with patch.object(multipart, "PART_BYTES", 8), patch.object(multipart, "upload_limit", tiny_limit):
                msg = await multipart.send_document(client, 1, original, "source.bin", "application/octet-stream")
                payload = json.loads(msg.data)
                bad = client.messages[payload["parts"][0]["message_id"]]
                bad.data = b"X" * len(bad.data)
                from fastapi import HTTPException
                with self.assertRaises(HTTPException):
                    await multipart.download_document(client, 1, msg.id, original.stat().st_size, recovered)

    async def test_legacy_single_document_still_downloads(self):
        client = FakeTelegram()
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / "tiny.bin"
            recovered = Path(folder) / "out.bin"
            original.write_bytes(b"abc")
            with patch.object(multipart, "upload_limit", tiny_limit):
                msg = await multipart.send_document(client, 1, original, "tiny.bin", "application/octet-stream")
                self.assertEqual(len(client.messages), 1)
                await multipart.download_document(client, 1, msg.id, 3, recovered)
            self.assertEqual(recovered.read_bytes(), b"abc")

    def test_invalid_manifest_type_fails_closed(self):
        from fastapi import HTTPException
        raw = json.dumps({"format":"drive-cloud-multipart","version":1,"size":9,
                          "parts":[{"message_id":1,"size":"bad","sha256":"a"*64},
                                   {"message_id":2,"size":9,"sha256":"a"*64}],
                          "sha256":"a"*64}).encode()
        with self.assertRaises(HTTPException):
            multipart.parse_manifest(raw, 9)


if __name__ == "__main__":
    unittest.main()
