"""HTTP byte range helpers for local Telegram media playback.

Deliberately independent of FastAPI and Telethon so tests can exercise the
HTTP and byte-count invariants without a live Telegram account.
"""
import inspect
import re

RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)\Z", re.ASCII)


class UnsatisfiableRange(ValueError):
    """Requested bytes are not available in the resource."""


class ShortMediaRead(IOError):
    """The remote provider returned fewer bytes than requested."""


def select_range(header, total, max_part):
    """Return (start, end, partial) for one RFC 7233 byte range.

    A single range is supported. We cap each part to limit RAM use and avoid
    holding a network response open while downloading the entire file.
    """
    if total <= 0 or max_part <= 0:
        raise UnsatisfiableRange("The media size is invalid.")
    if not header:
        return 0, total - 1, False

    match = RANGE_PATTERN.fullmatch(header.strip())
    if not match or not any(match.groups()):
        raise UnsatisfiableRange("Malformed or unsupported Range header.")

    first, last = match.groups()
    if first:
        start = int(first)
        end = int(last) if last else total - 1
    else:
        suffix = int(last)
        if suffix <= 0:
            raise UnsatisfiableRange("Invalid suffix range.")
        start = max(0, total - suffix)
        end = total - 1

    if start >= total or start > end or end >= total:
        raise UnsatisfiableRange("Range outside available media.")

    return start, min(end, start + max_part - 1), True


async def read_exact_range(client, file, start, count, request_size=128 * 1024):
    """Prefetch an exact byte range before returning HTTP response headers.

    Telethon handles unaligned offsets in iter_download. If the provider
    fails, we fail here rather than aborting an already-started 206 response.
    """
    if start < 0 or count < 1:
        raise ValueError("Invalid byte range.")
    if request_size <= 0 or request_size % 4096:
        raise ValueError("Telegram request_size must be a multiple of 4096.")

    iterator = client.iter_download(
        file, offset=start, request_size=request_size, chunk_size=request_size
    )
    data = bytearray()
    try:
        async for chunk in iterator:
            if not chunk:
                break
            needed = count - len(data)
            data.extend(chunk[:needed])
            if len(data) == count:
                break
    finally:
        close = getattr(iterator, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result

    if len(data) != count:
        raise ShortMediaRead(
            f"Telegram returned {len(data)} bytes; expected {count}."
        )
    return bytes(data)
