"""Validate actual image bytes, orient, bound dimensions and discard metadata."""
from io import BytesIO
import uuid
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageOps


def normalized_image(uploaded, *, max_edge):
    if uploaded.size > 5 * 1024 * 1024:
        raise ValidationError("Ảnh cần nhỏ hơn 5 MB.")
    formats = {"JPEG": (".jpg", "image/jpeg"), "PNG": (".png", "image/png"),
               "WEBP": (".webp", "image/webp")}
    try:
        uploaded.seek(0)
        with Image.open(uploaded) as image:
            image_format = image.format
            if image_format not in formats or image.width * image.height > 20_000_000:
                raise ValidationError("Chỉ dùng JPG, PNG hoặc WebP, tối đa 20 triệu điểm ảnh.")
            if getattr(image, "n_frames", 1) != 1:
                raise ValidationError("Hãy dùng ảnh tĩnh.")
            image.verify()
        uploaded.seek(0)
        with Image.open(uploaded) as image:
            image.load()
            pixels = ImageOps.exif_transpose(image)
            mode = "RGBA" if "A" in pixels.getbands() or "transparency" in pixels.info else "RGB"
            pixels = pixels.convert(mode if image_format != "JPEG" else "RGB")
            pixels.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
            cleaned = Image.frombytes(pixels.mode, pixels.size, pixels.tobytes())
            output = BytesIO()
            options = {"optimize": True} if image_format == "PNG" else {"quality": 85}
            cleaned.save(output, format=image_format, **options)
        if output.tell() > 5 * 1024 * 1024:
            raise ValidationError("Ảnh sau xử lý cần nhỏ hơn 5 MB.")
        extension, content_type = formats[image_format]
        return SimpleUploadedFile(uuid.uuid4().hex + extension, output.getvalue(), content_type=content_type)
    except (Image.DecompressionBombError, OSError, ValueError):
        raise ValidationError("Tệp không phải ảnh hợp lệ.")
    finally:
        uploaded.seek(0)
