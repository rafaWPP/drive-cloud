"""Tests for safe SQLite session diagnostics without exposing secrets."""
import sqlite3
import unittest

from server import safe_session_status_error


class TelegramSessionDiagnosticTests(unittest.TestCase):
    def test_database_locked_reports_actionable_reason(self):
        result = safe_session_status_error(sqlite3.OperationalError("database is locked"))
        self.assertEqual(result["code"], "SESSION_DATABASE_BUSY")
        self.assertIn("Feche outras instâncias", result["error"])

    def test_read_only_session_is_preserved(self):
        result = safe_session_status_error(sqlite3.OperationalError("attempt to write a readonly database"))
        self.assertEqual(result["code"], "SESSION_READ_ONLY")
        self.assertIn("Não exclua", result["error"])

    def test_disk_error_is_separate_from_authentication_failure(self):
        result = safe_session_status_error(sqlite3.OperationalError("disk I/O error"))
        self.assertEqual(result["code"], "SESSION_STORAGE_ERROR")

    def test_unknown_sqlite_error_does_not_leak_sql_or_paths(self):
        secret = "error while writing user_id='123456789' /home/private/telegram.session"
        result = safe_session_status_error(sqlite3.OperationalError(secret))
        self.assertEqual(result["code"], "SESSION_SQLITE_ERROR")
        self.assertNotIn("123456789", result["error"])
        self.assertNotIn("/home/private", result["error"])

    def test_other_errors_do_not_claim_user_logged_out(self):
        result = safe_session_status_error(TimeoutError("network"))
        self.assertEqual(result["code"], "TELEGRAM_CHECK_ERROR")
        self.assertIn("Não significa que a conta foi desconectada", result["error"])


if __name__ == "__main__":
    unittest.main()
