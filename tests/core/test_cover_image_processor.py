"""Actual image decoding and crop formats used by all three cover editors."""

from io import BytesIO

import pytest
from livingworld.application.world_covers import CoverCrop, CoverError
from livingworld.infrastructure.world_cover_images import PillowCoverImageProcessor
from PIL import Image


def image_bytes(fmt, *, size=(64, 48), orientation=None, animated=False):
    image = Image.new(
        "RGBA" if fmt != "JPEG" else "RGB",
        size,
        (40, 120, 210, 128) if fmt != "JPEG" else (40, 120, 210),
    )
    output = BytesIO()
    options = {}
    if orientation:
        exif = Image.Exif()
        exif[274] = orientation
        options["exif"] = exif
    if animated:
        options.update(
            save_all=True,
            append_images=[Image.new("RGBA", size, (220, 40, 30, 255))],
            duration=100,
            loop=0,
        )
    image.save(output, format=fmt, **options)
    return output.getvalue()


@pytest.mark.parametrize(
    "fmt,media", [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")]
)
def test_supported_uploads_decode_and_crop_to_real_webp(fmt, media):
    processor = PillowCoverImageProcessor()
    data = image_bytes(fmt)
    assert processor.inspect(data) == {"media_type": media, "width": 64, "height": 48}
    # Source and output are both 4:3, so this is a full-face crop.
    rendered = processor.render(data, CoverCrop(0, 0, 100, 100), (320, 240))
    assert processor.inspect(rendered) == {"media_type": "image/webp", "width": 320, "height": 240}
    with Image.open(BytesIO(rendered)) as result:
        result.load()
        if fmt != "JPEG":
            assert result.convert("RGBA").getpixel((160, 120))[3] == 128


@pytest.mark.parametrize("fmt", ["JPEG", "WEBP"])
def test_exif_rotation_is_applied_before_crop(fmt):
    processor = PillowCoverImageProcessor()
    data = image_bytes(fmt, orientation=6)
    assert processor.inspect(data)["width"] == 48
    assert processor.inspect(data)["height"] == 64
    result = processor.render(data, CoverCrop(0, 0, 100, 100), (240, 320))
    assert processor.inspect(result)["width"] == 240


@pytest.mark.parametrize(
    "data,code",
    [
        (b"synthetic-invalid", "cover_image_invalid"),
        (image_bytes("PNG", size=(10001, 1)), "cover_image_dimensions_limit"),
        (image_bytes("WEBP", animated=True), "cover_image_dimensions_limit"),
    ],
)
def test_invalid_oversized_and_animated_uploads_remain_rejected(data, code):
    with pytest.raises(CoverError, match=code):
        PillowCoverImageProcessor().inspect(data)


def test_crop_bounds_remain_enforced():
    with pytest.raises(CoverError, match="cover_crop_invalid"):
        PillowCoverImageProcessor().render(
            image_bytes("PNG"), CoverCrop(50, 0, 100, 100), (320, 240)
        )
