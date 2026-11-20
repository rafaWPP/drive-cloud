"""Entry point for the packaged, localhost-only Drive Cloud connector."""
import os
import sys
import threading
import traceback
from datetime import datetime, timezone
from pathlib import Path

def main():
    data = Path(os.environ.get("DRIVE_CLOUD_DATA_DIR") or Path.home() / ".local/share/drive-cloud")
    data.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        data.chmod(0o700)
    except OSError:
        pass
    log_file = data / "backend-startup.log"
    # This diagnostic log must not contain phone numbers, API hashes or tokens.
    def report(message):
        try:
            with log_file.open("a", encoding="utf-8") as f:
                f.write(f"{datetime.now(timezone.utc).isoformat()} {message}\n")
            log_file.chmod(0o600)
        except OSError:
            pass

    report("Starting local Drive Cloud connector")
    try:
        from dotenv import load_dotenv
        load_dotenv(data / ".env", override=False)
        import server
        import uvicorn
        port = int(os.environ.get("DRIVE_CLOUD_BACKEND_PORT", "8000"))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid local backend port")
        report(f"Imported server module; binding to loopback port {port}")
        config = uvicorn.Config(server.app, host="127.0.0.1", port=port,
                                reload=False, workers=1, access_log=False)
        api = uvicorn.Server(config)

        def listen_for_desktop_shutdown():
            """Both Linux and Windows Tauri close the sidecar through stdin.

            The server's normal shutdown awaits Telethon.disconnect() so its
            SQLite session is committed instead of being killed mid-write.
            Ignore EOF: CI and terminal launches may have closed stdin.
            """
            try:
                for line in sys.stdin:
                    if line.strip() == "drive-cloud:shutdown":
                        report("Desktop requested graceful shutdown")
                        api.should_exit = True
                        return
            except (OSError, ValueError, TypeError):
                return

        if sys.stdin is not None:
            threading.Thread(target=listen_for_desktop_shutdown,
                             name="drive-cloud-shutdown", daemon=True).start()
        api.run()
        report("Server stopped")
    except BaseException as exc:
        report(f"Startup failed: {type(exc).__name__}: {str(exc)[:300]}")
        report("".join(traceback.format_exception(type(exc), exc, exc.__traceback__))[-4000:])
        raise

if __name__ == "__main__":
    main()
