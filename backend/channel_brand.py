"""Build the exact Drive Cloud logo as a Telegram-compatible square JPEG.

The brand data is extracted from public/drive-cloud-logo.svg at build time.
Keeping the embedded base64 here ensures the Telegram sidecar has the same
logo even when the desktop frontend assets are not bundled in PyInstaller.
"""
import base64
import io
from PIL import Image, ImageOps

LOGO_WEBP_BASE64 = (
    "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"
    "Zd2zdErAqpf/+5MQ5IVVAAAAAAA="
)

def channel_avatar_jpeg() -> bytes:
    """Render the application logo as a 512x512 JPEG for channel avatars."""
    raw = base64.b64decode(LOGO_WEBP_BASE64, validate=True)
    with Image.open(io.BytesIO(raw)) as original:
        image = ImageOps.exif_transpose(original)
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        image = image.resize((512, 512), Image.Resampling.LANCZOS)
        background = Image.new("RGB", (512, 512), "#17273E")
        background.paste(image, (0, 0), image.getchannel("A"))
        output = io.BytesIO()
        background.save(output, format="JPEG", quality=94, subsampling=0)
        return output.getvalue()
