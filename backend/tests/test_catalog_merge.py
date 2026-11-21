import sqlite3
import unittest
import uuid

from fastapi import HTTPException
from catalog_merge import merge_catalog


class CatalogMergeSafetyTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE nodes(
            id TEXT PRIMARY KEY, account TEXT NOT NULL,
            kind TEXT NOT NULL, parent TEXT,
            name TEXT NOT NULL, size INTEGER NOT NULL, mime TEXT NOT NULL,
            message_id INTEGER, created INTEGER NOT NULL,
            trashed INTEGER NOT NULL DEFAULT 0, starred INTEGER NOT NULL DEFAULT 0)""")
        self.root_id = str(uuid.uuid4())
        self.file_id = str(uuid.uuid4())
        self.base = {"format": "drive-cloud-catalog", "version": 1,
                     "telegram_account": "42", "channel_id": "123",
                     "items": [
                         {"id": self.root_id, "kind": "folder", "parent": None,
                          "name": "Backup • Teste", "size": 0,
                          "mime": "application/octet-stream", "message_id": None,
                          "created": 100, "trashed": 0, "starred": 0},
                         {"id": self.file_id, "kind": "file", "parent": self.root_id,
                          "name": "report.pdf", "size": 5, "mime": "application/pdf",
                          "message_id": 55, "created": 101, "trashed": 0, "starred": 0},
                     ]}

    def tearDown(self):
        self.db.close()

    def test_additive_and_idempotent(self):
        with self.db:
            first = merge_catalog(self.db, self.base, "42", 123)
        self.assertEqual(first["imported"], 2)
        with self.db:
            second = merge_catalog(self.db, self.base, "42", 123)
        self.assertEqual(second["imported"], 0)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 2)

    def test_different_account_channel_rejected(self):
        with self.assertRaises(HTTPException) as exc:
            merge_catalog(self.db, self.base, "43", 123)
        self.assertEqual(exc.exception.status_code, 409)
        with self.assertRaises(HTTPException) as exc:
            merge_catalog(self.db, self.base, "42", 456)
        self.assertEqual(exc.exception.status_code, 409)

    def test_existing_metadata_not_overwritten(self):
        with self.db:
            merge_catalog(self.db, self.base, "42", 123)
        divergent = {"format": "drive-cloud-catalog", "version": 1,
                     "telegram_account": "42", "channel_id": "123",
                     "items": [{**row} for row in self.base["items"]]}
        divergent["items"][1]["name"] = "renamed.pdf"
        with self.db:
            result = merge_catalog(self.db, divergent, "42", 123)
        self.assertEqual(result["metadata_differences_preserved"], 1)
        self.assertEqual(self.db.execute(
            "SELECT name FROM nodes WHERE id=?", (self.file_id,)).fetchone()["name"], "report.pdf")

    def test_cycles_rejected_before_insert(self):
        bad = {"format": "drive-cloud-catalog", "version": 1,
               "telegram_account": "42", "channel_id": "123",
               "items": [{**row} for row in self.base["items"]]}
        bad["items"][0]["parent"] = self.file_id
        with self.assertRaises(HTTPException) as exc:
            merge_catalog(self.db, bad, "42", 123)
        self.assertEqual(exc.exception.status_code, 422)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 0)

    def test_duplicate_node_rejected(self):
        duplicated = {**self.base, "items": self.base["items"] * 2}
        with self.assertRaises(HTTPException):
            merge_catalog(self.db, duplicated, "42", 123)

    def test_dry_run_never_writes(self):
        result = merge_catalog(self.db, self.base, "42", 123, dry_run=True)
        self.assertEqual(result["new_items"], 2)
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM nodes").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
