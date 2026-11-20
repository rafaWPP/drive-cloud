"""Offline regression tests for local Telegram byte-range responses."""
import asyncio
import unittest

from media_ranges import (
    select_range, read_exact_range, UnsatisfiableRange, ShortMediaRead
)


class RangeSelectionTests(unittest.TestCase):
    def test_open_ended_request_is_capped(self):
        self.assertEqual(select_range("bytes=0-", 1024 * 1024, 128 * 1024),
                         (0, 128 * 1024 - 1, True))

    def test_seek_start_and_explicit_end(self):
        self.assertEqual(select_range("bytes=120-199", 1024, 256),
                         (120, 199, True))

    def test_suffix_range(self):
        self.assertEqual(select_range("bytes=-10", 100, 20),
                         (90, 99, True))

    def test_no_range_gives_full_200(self):
        self.assertEqual(select_range(None, 99, 16), (0, 98, False))

    def test_invalid_ranges(self):
        headers = ("bytes=0-1,3-4", "bytes=-0", "bytes=800-",
                   "bytes=12-2", "bytes=letters", "bytes=")
        for header in headers:
            with self.subTest(header=header):
                with self.assertRaises(UnsatisfiableRange):
                    select_range(header, 700, 128)
        with self.assertRaises(UnsatisfiableRange):
            select_range("bytes=0-", 0, 128)

    def test_unaligned_requested_offset(self):
        self.assertEqual(select_range("bytes=4099-8199", 10000, 4096),
                         (4099, 8199, True))


class FakeClient:
    def __init__(self, data, max_chunk=4096):
        self.data = data
        self.max_chunk = max_chunk
        self.offsets = []

    def iter_download(self, file, *, offset, request_size, chunk_size):
        self.offsets.append(offset)

        async def iterate():
            for start in range(offset, len(self.data), self.max_chunk):
                yield self.data[start:start + self.max_chunk]
        return iterate()


class ExactReadTests(unittest.TestCase):
    def test_exact_fetch_never_returns_extra_data(self):
        data = bytes(range(256)) * 400
        client = FakeClient(data, max_chunk=4096)
        result = asyncio.run(read_exact_range(client, "test-media", 123, 66000))
        self.assertEqual(result, data[123:66123])
        self.assertEqual(client.offsets, [123])

    def test_small_probe(self):
        data = b"abcdefghij"
        client = FakeClient(data)
        self.assertEqual(asyncio.run(
            read_exact_range(client, "test-media", 0, 1)
        ), b"a")

    def test_short_read_raises_before_response(self):
        client = FakeClient(b"only ten!")
        with self.assertRaises(ShortMediaRead):
            asyncio.run(read_exact_range(client, "test", 0, 60))

    def test_request_size_alignment(self):
        with self.assertRaises(ValueError):
            asyncio.run(read_exact_range(FakeClient(b"x" * 100),
                                         "test", 0, 1, request_size=5000))


if __name__ == "__main__":
    unittest.main()
