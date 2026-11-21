"""Conservative MTProto file size limits per Telegram account tier.

Maximum individual document size is bounded by the number of 512 KiB parts
the Telegram server accepts: 4000 Free and 8000 Premium. Leave one part of
headroom; larger backup archives need a separate multi-message format.
"""
PART_BYTES = 512 * 1024
FREE_MAX_FILE = 3999 * PART_BYTES
PREMIUM_MAX_FILE = 7999 * PART_BYTES

async def upload_limit(client):
    user = await client.get_me()
    return PREMIUM_MAX_FILE if bool(getattr(user, "premium", False)) else FREE_MAX_FILE

def readable_limit(value):
    return "4 GB (Telegram Premium)" if value > FREE_MAX_FILE else "2 GB (Telegram gratuito)"
