import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from fastapi import HTTPException
from sync_reconcile import (
    decision, install_download, remote_tree, safe_relative, safe_segment,
)


class TwoWaySyncSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE nodes (
            id TEXT PRIMARY KEY, account TEXT NOT NULL, parent TEXT, name TEXT,
            kind TEXT, size INTEGER, message_id INTEGER,
            created INTEGER, trashed INTEGER NOT NULL DEFAULT 0)""")
        self.root_id = str(uuid.uuid4())
        self.db.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?)",
                        (self.root_id, "account", None, "Backup • Fotos", "folder", 0, None, 1, 0))

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_safe_path_blocks_traversal_and_symlinks(self):
        for name in ("..", ".", "a/b", "a\\b", "CON.txt", "secret:", "bad\x00name", "lpt1"):
            with self.subTest(name=name):
                with self.assertRaises(HTTPException):
                    safe_segment(name)
        outside = self.root / "shortcut"
        outside.symlink_to(self.root.parent, target_is_directory=True)
        with self.assertRaises(HTTPException):
            safe_relative(self.root, ["shortcut", "other.txt"])

    def test_remote_tree_only_account_active_versions(self):
        old = str(uuid.uuid4())
        recent = str(uuid.uuid4())
        other = str(uuid.uuid4())
        self.db.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?)",
                        (old, "account", self.root_id, "photo.jpg", "file", 3, 10, 10, 0))
        self.db.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?)",
                        (recent, "account", self.root_id, "photo.jpg", "file", 4, 11, 20, 0))
        self.db.execute("INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?)",
                        (other, "another", self.root_id, "private.jpg", "file", 10, 12, 30, 0))
        active = remote_tree(self.db, "account", self.root_id)
        self.assertEqual(set(active), {"photo.jpg"})
        self.assertEqual(active["photo.jpg"]["id"], recent)
        self.assertEqual(active["photo.jpg"]["message_id"], 11)

    def test_remote_copy_never_overwrites_local_file(self):
        remote = self.root / "remote.bin"
        remote.write_bytes(b"from Telegram")
        destination = self.root / "report.txt"
        destination.write_bytes(b"local modification")
        remote_id = str(uuid.uuid4())
        result, copied = install_download(remote, destination, self.root, remote_id)
        self.assertEqual(result, "conflict_saved")
        self.assertEqual(destination.read_bytes(), b"local modification")
        self.assertIn("Telegram-", copied.name)
        self.assertEqual(copied.read_bytes(), b"from Telegram")
        again, same_copy = install_download(remote, destination, self.root, remote_id)
        self.assertEqual(again, "conflict_existing")
        self.assertEqual(same_copy, copied)

    def test_missing_remote_file_is_created_without_overwrite(self):
        remote = self.root / "remote.bin"
        remote.write_bytes(b"saved")
        dest = self.root / "nested" / "report.txt"
        result, saved = install_download(remote, dest, self.root, str(uuid.uuid4()))
        self.assertEqual(result, "downloaded")
        self.assertEqual(saved.read_bytes(), b"saved")
        self.assertEqual(decision(dest, "remote-node", None), "compare")

    def test_identical_remote_does_not_create_copy(self):
        remote = self.root / "remote.bin"
        remote.write_bytes(b"unchanged")
        destination = self.root / "report.txt"
        destination.write_bytes(b"unchanged")
        result, path = install_download(remote, destination, self.root, str(uuid.uuid4()))
        self.assertEqual(result, "identical")
        self.assertEqual(path, destination)
        self.assertEqual(list(self.root.iterdir()), [remote, destination])

    def test_local_directories_are_never_replaced(self):
        directory = self.root / "report.txt"
        directory.mkdir()
        self.assertEqual(decision(directory, "node"), "unsafe")


if __name__ == "__main__":
    unittest.main()
