"""Channel branding tests: only blank owned channels may get Drive Cloud's logo."""
import io
import unittest
from types import SimpleNamespace

from PIL import Image
from telethon.tl.functions.channels import EditPhotoRequest
from telethon.tl.types import ChatPhotoEmpty, InputChatUploadedPhoto

from channel_brand import LOGO_WEBP_BASE64, channel_avatar_jpeg
from server import assign_drive_channel_logo


class ChannelBrandImageTests(unittest.TestCase):
    def test_photo_uses_bundled_brand_and_is_valid_jpeg(self):
        self.assertGreater(len(LOGO_WEBP_BASE64), 1000)
        data = channel_avatar_jpeg()
        self.assertTrue(data.startswith(bytes.fromhex("ffd8")))
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (512, 512))


class MockTelegramClient:
    def __init__(self, fail=False):
        self.uploads = []
        self.edits = []
        self.fail = fail

    async def upload_file(self, file):
        if self.fail:
            raise RuntimeError("Telegram rejects photo uploads")
        self.uploads.append((file.name, file.getvalue()))
        return object()

    async def __call__(self, request):
        self.edits.append(request)
        return None


class ChannelBrandRequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_private_channel_receives_logo(self):
        channel = SimpleNamespace(creator=True, photo=ChatPhotoEmpty())
        client = MockTelegramClient()
        result = await assign_drive_channel_logo(client, channel)
        self.assertTrue(result)
        self.assertEqual(len(client.uploads), 1)
        self.assertEqual(client.uploads[0][0], "drive-cloud-channel.jpg")
        self.assertEqual(len(client.edits), 1)
        self.assertIsInstance(client.edits[0], EditPhotoRequest)
        self.assertIsInstance(client.edits[0].photo, InputChatUploadedPhoto)

    async def test_custom_photo_is_never_overwritten(self):
        channel = SimpleNamespace(creator=True, photo=object())
        client = MockTelegramClient()
        self.assertFalse(await assign_drive_channel_logo(client, channel))
        self.assertEqual(client.uploads, [])
        self.assertEqual(client.edits, [])

    async def test_not_owned_channel_is_not_modified(self):
        channel = SimpleNamespace(creator=False, photo=ChatPhotoEmpty())
        client = MockTelegramClient()
        self.assertFalse(await assign_drive_channel_logo(client, channel))
        self.assertEqual(client.edits, [])

    async def test_photo_failure_does_not_block_storage(self):
        channel = SimpleNamespace(creator=True, photo=None)
        client = MockTelegramClient(fail=True)
        self.assertFalse(await assign_drive_channel_logo(client, channel))
        self.assertEqual(client.edits, [])


if __name__ == "__main__":
    unittest.main()
