import sqlite3
import unittest
from fastapi import HTTPException

from catalog_telegram import catalog_payload, decode_catalog, encode_catalog, MAX_SNAPSHOT_BYTES


class CatalogTelegramTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        self.db.execute("""CREATE TABLE nodes (
          id TEXT, account TEXT, kind TEXT, parent TEXT, name TEXT,
          size INTEGER, mime TEXT, message_id INTEGER, created INTEGER,
          trashed INTEGER, starred INTEGER)""")
        self.db.execute(
            "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("11111111-1111-4111-8111-111111111111", "42", "folder", None,
             "Trabalho", 0, "application/octet-stream", None, 1, 0, 0),
        )

    def tearDown(self):
        self.db.close()

    def test_snapshot_round_trip(self):
        payload = catalog_payload(self.db, "42", 456)
        restored = decode_catalog(encode_catalog(payload), "42", 456)
        self.assertEqual(len(restored["items"]), 1)
        self.assertEqual(restored["items"][0]["name"], "Trabalho")

    def test_other_account_and_channel_rejected(self):
        raw = encode_catalog(catalog_payload(self.db, "42", 456))
        for account, channel in [("43", 456), ("42", 457)]:
            with self.subTest(account=account, channel=channel):
                with self.assertRaises(HTTPException) as exc:
                    decode_catalog(raw, account, channel)
                self.assertEqual(exc.exception.status_code, 409)

    def test_invalid_payload_rejected(self):
        with self.assertRaises(HTTPException) as exc:
            decode_catalog(b"not a json document", "42", 456)
        self.assertEqual(exc.exception.status_code, 422)

    def test_oversized_rejected(self):
        with self.assertRaises(HTTPException) as exc:
            decode_catalog(b"x" * (MAX_SNAPSHOT_BYTES + 1), "42", 456)
        self.assertEqual(exc.exception.status_code, 413)

    def test_filters_other_accounts(self):
        self.db.execute(
            "INSERT INTO nodes VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("22222222-2222-4222-8222-222222222222", "other", "folder", None,
             "Segredo", 0, "application/octet-stream", None, 2, 0, 0),
        )
        payload = catalog_payload(self.db, "42", 456)
        self.assertEqual([x["name"] for x in payload["items"]], ["Trabalho"])


if __name__ == "__main__":
    unittest.main()
