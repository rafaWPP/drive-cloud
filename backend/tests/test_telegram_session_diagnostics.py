"""Tests for safe SQLite session diagnostics without exposing secrets."""
import sqlite3
import unittest
from unittest.mock import AsyncMock, patch

import server
from server import safe_session_status_error


class TelegramSessionDiagnosticTests(unittest.TestCase):
    def test_database_locked_reports_actionable_reason(self):
        result = safe_session_status_error(sqlite3.OperationalError("database is locked"))
        self.assertEqual(result["code"], "SESSION_DATABASE_BUSY")
        self.assertIn("Feche todas as janelas", result["error"])

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


class FailedSessionCleanupTests(unittest.IsolatedAsyncioTestCase):
    async def test_failed_sqlite_session_is_closed_without_logging_out(self):
        class MockSession:
            def __init__(self):
                self.closed = 0

            def close(self):
                self.closed += 1

        class MockTelegram:
            def __init__(self):
                self.session = MockSession()
                self.disconnect_calls = 0
                self.logout_calls = 0

            async def disconnect(self):
                self.disconnect_calls += 1

            async def log_out(self):
                self.logout_calls += 1

        fake = MockTelegram()
        previous = server.client
        server.client = fake
        try:
            await server.release_failed_session_client()
            self.assertIsNone(server.client)
            self.assertEqual(fake.disconnect_calls, 1)
            self.assertEqual(fake.session.closed, 1)
            self.assertEqual(fake.logout_calls, 0)
        finally:
            server.client = previous

    async def test_sqlite_status_error_cleans_client_but_keeps_session_file(self):
        class MockSession:
            def __init__(self):
                self.closed = 0

            def close(self):
                self.closed += 1

        class MockTelegram:
            def __init__(self):
                self.session = MockSession()
                self.disconnect_calls = 0

            async def disconnect(self):
                self.disconnect_calls += 1

        fake = MockTelegram()
        previous = server.client
        server.client = fake
        with patch.object(server, "API_ID", 12345), patch.object(
            server, "API_HASH", "0" * 32
        ), patch.object(
            server, "connected_client", new=AsyncMock(
                side_effect=sqlite3.OperationalError("database is locked")
            )
        ):
            try:
                status = await server.status()
                self.assertEqual(status["code"], "SESSION_DATABASE_BUSY")
                self.assertIsNone(server.client)
                self.assertEqual(fake.session.closed, 1)
                self.assertEqual(fake.disconnect_calls, 1)
            finally:
                server.client = previous


if __name__ == "__main__":
    unittest.main()
