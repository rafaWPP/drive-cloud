"""Smoke-test a packaged Drive Cloud connector on BOTH desktop OSes.

Launch -> wait for health -> gracefully stop -> launch again on the same data
directory. Uses an isolated temporary directory; never reads a real session.
Run: python backend/tests/check_sidecar_lifecycle.py <path-to-sidecar>
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

SHUTDOWN_COMMAND = b"drive-cloud:shutdown\n"


def free_loopback_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_health(process, origin, timeout=70):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if process.poll() is not None:
            raise RuntimeError("Connector exited early with code " + str(process.returncode))
        try:
            with urllib.request.urlopen(origin + "/api/health", timeout=1) as response:
                payload = json.load(response)
            if payload.get("ready") is True:
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        time.sleep(.4)
    raise TimeoutError("Connector never exposed the local health endpoint")


def test_lifecycle(executable: Path):
    assert executable.is_file(), f"Sidecar executable does not exist: {executable}"
    with tempfile.TemporaryDirectory(prefix="dc-sidecar-restart-") as temporary:
        data_dir = Path(temporary)
        port = free_loopback_port()
        origin = f"http://127.0.0.1:{port}"
        env = dict(os.environ)
        env["DRIVE_CLOUD_DATA_DIR"] = str(data_dir)
        env["DRIVE_CLOUD_BACKEND_PORT"] = str(port)
        # Empty credentials in this isolated test: no Telegram account touched.
        env.pop("TELEGRAM_API_ID", None)
        env.pop("TELEGRAM_API_HASH", None)

        for attempt in (1, 2):
            with subprocess.Popen(
                [str(executable)], env=env, stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            ) as process:
                try:
                    wait_for_health(process, origin)
                    with urllib.request.urlopen(origin + "/api/telegram/status", timeout=2) as reply:
                        status = json.load(reply)
                    assert status["configured"] is False, status
                    # A second packaged connector must never open the same
                    # Telethon SQLite session concurrently, even on a new port.
                    other_env = dict(env)
                    other_env["DRIVE_CLOUD_BACKEND_PORT"] = str(free_loopback_port())
                    with subprocess.Popen(
                        [str(executable)], env=other_env, stdin=subprocess.PIPE,
                        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                    ) as second:
                        try:
                            second.wait(timeout=20)
                            assert second.returncode != 0, (
                                "Second process should be refused while the first holds the session lock"
                            )
                            with urllib.request.urlopen(origin + "/api/health", timeout=2) as alive:
                                assert json.load(alive).get("ready") is True
                        finally:
                            if second.poll() is None:
                                second.kill()
                                second.wait(timeout=10)
                    assert process.stdin is not None
                    process.stdin.write(SHUTDOWN_COMMAND)
                    process.stdin.flush()
                    process.wait(timeout=20)
                    assert process.returncode == 0, (
                        f"Sidecar shutdown failed on attempt {attempt}: {process.returncode}"
                    )
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=10)
            print(f"Sidecar start/health/graceful stop #{attempt}: OK", flush=True)

        startup_log = data_dir / "backend-startup.log"
        assert startup_log.exists(), "Expected sidecar diagnostic log"
        log = startup_log.read_text(encoding="utf-8")
        assert log.count("Exclusive Telegram session directory lock acquired") == 2, (
            "Expected exactly two successful exclusive session locks"
        )
        assert "RuntimeError" in log, "Expected duplicate-instance refusal in startup diagnostic"
        assert log.count("Desktop requested graceful shutdown") == 2, (
            "Desktop sidecar did not receive graceful shutdown on both runs"
        )
        assert log.count("Server stopped") == 2, (
            "Uvicorn did not complete a clean shutdown on both runs"
        )
        print("Packaged sidecar lifecycle on this OS: PASS")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: check_sidecar_lifecycle.py <sidecar-executable>")
    test_lifecycle(Path(sys.argv[1]).resolve())
