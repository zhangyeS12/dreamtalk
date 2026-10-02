"""Pillow image decoding, EXIF orientation and fixed-aspect local cover rendering."""

from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError

from livingworld.application.world_covers import CoverError

MEDIA = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
MAX_PIXELS = 20_000_000


class PillowCoverImageProcessor:
    def _open(self, data):
        try:
            image = Image.open(BytesIO(data), formats=list(MEDIA))
            if (
                image.width * image.height > MAX_PIXELS
                or max(image.size) > 10000
                or getattr(image, "n_frames", 1) != 1
            ):
                image.close()
                raise CoverError("cover_image_dimensions_limit")
            return image
        except CoverError:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
            raise CoverError("cover_image_invalid") from error

    def inspect(self, data):
        with self._open(data) as image:
            media_type = MEDIA[image.format]
            try:
                image.verify()
            except (OSError, ValueError, SyntaxError) as error:
                raise CoverError("cover_image_invalid") from error
        with self._open(data) as image:
            try:
                oriented = ImageOps.exif_transpose(image)
                oriented.load()
                return {
                    "media_type": media_type,
                    "width": oriented.width,
                    "height": oriented.height,
                }
            except (OSError, ValueError, SyntaxError) as error:
                raise CoverError("cover_image_invalid") from error

    def render(self, data, crop, size):
        with self._open(data) as image:
            oriented = ImageOps.exif_transpose(image).convert("RGBA")
        rotated = oriented.rotate(-crop.rotation, expand=True)
        width, height = rotated.size
        if (
            crop.x + crop.width > 100.01
            or crop.y + crop.height > 100.01
            or abs((crop.width * width / (crop.height * height)) / (size[0] / size[1]) - 1) > 0.015
        ):
            raise CoverError("cover_crop_invalid")
        box = (
            crop.x * width / 100,
            crop.y * height / 100,
            min(100, crop.x + crop.width) * width / 100,
            min(100, crop.y + crop.height) * height / 100,
        )
        output = rotated.resize(size, Image.Resampling.LANCZOS, box=box)
        buffer = BytesIO()
        output.save(buffer, format="WEBP", quality=90, method=4)
        return buffer.getvalue()
