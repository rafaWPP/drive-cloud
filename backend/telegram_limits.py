"""Telegram account upload size limits.

Keep a small margin below the nominal limit for consistency across clients.
These limits apply to each Telegram document, not an entire backup folder.
"""
FREE_MAX_FILE = 2 * 1024 * 1024 * 1024 - 1024 * 1024
PREMIUM_MAX_FILE = 4 * 1024 * 1024 * 1024 - 1024 * 1024

async def upload_limit(client):
    user = await client.get_me()
    return PREMIUM_MAX_FILE if bool(getattr(user, "premium", False)) else FREE_MAX_FILE

def readable_limit(value):
    return "4 GB (Telegram Premium)" if value > FREE_MAX_FILE else "2 GB (Telegram gratuito)"
