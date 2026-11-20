import hashlib
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi import HTTPException
from resumable_upload import (
    CHUNK_SIZE, apply_chunk, check_name, file_size,
    get_session, row_status, schema, stage_path,
)


class ResumableUploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.part"
        self.path.write_bytes(b"")
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        schema(self.db)

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def append(self, offset, payload, expected=1024):
        return apply_chunk(self.path, offset, expected, payload,
                           hashlib.sha256(payload).hexdigest())

    def test_resume_after_reopening_staged_file(self):
        self.assertEqual(self.append(0, b"hello"), 5)
        self.assertEqual(file_size(self.path), 5)
        # New call uses the existing file length; the earlier block is not repeated.
        self.assertEqual(self.append(5, b" world"), 11)
        self.assertEqual(self.path.read_bytes(), b"hello world")

    def test_same_chunk_can_be_retried_after_lost_ack(self):
        self.assertEqual(self.append(0, b"first"), 5)
        self.assertEqual(self.append(0, b"first"), 5)
        self.assertEqual(self.path.read_bytes(), b"first")

    def test_changed_duplicate_and_out_of_order_are_rejected(self):
        self.append(0, b"first")
        for offset, payload in [(0, b"other"), (9, b"new"), (3, b"overlap")]:
            with self.subTest(offset=offset):
                with self.assertRaises(HTTPException) as exc:
                    self.append(offset, payload)
                self.assertEqual(exc.exception.status_code, 409)
        self.assertEqual(self.path.read_bytes(), b"first")

    def test_invalid_sha_is_rejected_without_writing(self):
        with self.assertRaises(HTTPException) as exc:
            apply_chunk(self.path, 0, 100, b"hello", "0" * 64)
        self.assertEqual(exc.exception.status_code, 422)
        self.assertEqual(self.path.read_bytes(), b"")

    def test_file_size_limit_is_enforced(self):
        with self.assertRaises(HTTPException) as exc:
            self.append(0, b"12345", 4)
        self.assertEqual(exc.exception.status_code, 416)
        with self.assertRaises(HTTPException) as exc:
            self.append(0, b"x" * (CHUNK_SIZE + 1), CHUNK_SIZE + 5)
        self.assertEqual(exc.exception.status_code, 413)

    def test_staged_file_symlink_is_rejected(self):
        outside = Path(self.temp.name) / "target"
        outside.write_text("private")
        pointer = Path(self.temp.name) / "link.part"
        pointer.symlink_to(outside)
        with self.assertRaises(HTTPException) as exc:
            self.append_to_path(pointer)
        self.assertEqual(exc.exception.status_code, 409)
        self.assertEqual(outside.read_text(), "private")

    def append_to_path(self, path):
        apply_chunk(path, 0, 100, b"hello", hashlib.sha256(b"hello").hexdigest())

    def test_upload_id_cannot_traverse_paths(self):
        with self.assertRaises(ValueError):
            stage_path("../private")
        self.assertEqual(stage_path(uuid.uuid4()).suffix, ".part")

    def test_account_and_channel_bound_to_upload(self):
        id_ = str(uuid.uuid4())
        self.db.execute(
            "INSERT INTO resumable_uploads "
            "(id,account,channel,parent,name,size,mime,signature,updated) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (id_, "account-A", "111", None, "photo.jpg", 10, "image/jpeg", "a" * 64, 123),
        )
        row = get_session(self.db, id_, "account-A", 111)
        self.assertEqual(row_status(row, 5)["offset"], 5)
        for account, channel in [("account-B", 111), ("account-A", 222)]:
            with self.assertRaises(HTTPException) as exc:
                get_session(self.db, id_, account, channel)
            self.assertEqual(exc.exception.status_code, 404)

    def test_reject_unsafe_filenames(self):
        for name in ["a/b", "a\\b", "..", " ", "bad\x00file"]:
            with self.subTest(name=repr(name)):
                with self.assertRaises(HTTPException):
                    check_name(name)
