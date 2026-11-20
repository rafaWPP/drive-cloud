"""Packaged, loopback-only Telegram connector for the desktop app.

The bundled executable must not bind to a public network interface.
Credentials are read from the user's local configuration (never embedded here).
"""
import os
from pathlib import Path
import uvicorn

def main():
    data = Path(os.environ.get("DRIVE_CLOUD_DATA_DIR") or Path.home() / ".local/share/drive-cloud")
    data.mkdir(mode=0o700, parents=True, exist_ok=True)
    # Enables testing with a private per-user configuration, without shipping
    # an API hash in the public repository or reading backend/.env inside a bundle.
    from dotenv import load_dotenv
    load_dotenv(data / ".env", override=False)
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False, workers=1, access_log=False)

if __name__ == "__main__":
    main()
