import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from folder_sync import (
    ensure_schema, scan_folder, source_root, pending_files,
    ensure_remote_folder, MAX_SIZE
)


class FolderSyncSafetyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE nodes (
            id TEXT PRIMARY KEY, account TEXT, kind TEXT, parent TEXT, name TEXT,
            size INTEGER DEFAULT 0, mime TEXT DEFAULT 'application/octet-stream',
            message_id INTEGER, created INTEGER, trashed INTEGER DEFAULT 0,
            starred INTEGER DEFAULT 0)""")
        ensure_schema(self.db)

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_symlinks_and_build_folders_not_scanned(self):
        (self.root / "photo.jpg").write_bytes(b"photo")
        (self.root / "node_modules").mkdir()
        (self.root / "node_modules" / "secret.txt").write_text("ignore")
        (self.root / "scratch.tmp").write_text("ignore")
        (self.root / "link").symlink_to(self.root / "photo.jpg")
        files, oversized = scan_folder(self.root)
        self.assertEqual([x[0] for x in files], ["photo.jpg"])
        self.assertEqual(oversized, 0)

    def test_oversized_files_skipped(self):
        path = self.root / "huge.bin"
        with path.open("wb") as stream:
            stream.truncate(MAX_SIZE + 1)
        files, oversized = scan_folder(self.root)
        self.assertEqual(files, [])
        self.assertEqual(oversized, 1)

    def test_root_and_symlink_root_rejected(self):
        with self.assertRaises(HTTPException):
            source_root("/")
        link = self.root.parent / ("drive-cloud-symlink-" + self.root.name)
        try:
            link.symlink_to(self.root, target_is_directory=True)
            with self.assertRaises(HTTPException):
                source_root(str(link))
        finally:
            link.unlink(missing_ok=True)

    def test_pending_files_only_new_or_changed(self):
        self.db.execute(
            "INSERT INTO sync_folders(id,account,path,root_node) VALUES (?,?,?,?)",
            ("sync-1", "account", str(self.root), "root-node"))
        self.db.execute(
            "INSERT INTO sync_entries(folder_id,rel_path,node_id,size,mtime_ns) "
            "VALUES (?,?,?,?,?)", ("sync-1", "one.txt", "file-1", 4, 123))
        folder = self.db.execute("SELECT * FROM sync_folders WHERE id='sync-1'").fetchone()
        scanned = [("one.txt", 4, 123), ("two.txt", 5, 456)]
        self.assertEqual(pending_files(self.db, folder, scanned), [("two.txt", 5, 456)])
        self.assertEqual(pending_files(self.db, folder, [("one.txt", 6, 789)]),
                         [("one.txt", 6, 789)])
        # Missing local files must never trigger a remote deletion.
        self.assertEqual(pending_files(self.db, folder, []), [])

    def test_remote_folder_not_duplicated(self):
        first = ensure_remote_folder(self.db, "account", None, "Photos", 123)
        second = ensure_remote_folder(self.db, "account", None, "Photos", 124)
        self.assertEqual(first, second)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
