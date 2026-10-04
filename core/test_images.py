from io import BytesIO
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image, PngImagePlugin
from core.forms import ProfileForm
from core.images import normalized_image
from journey.forms import ImageUploadForm


class NormalizedImageTests(SimpleTestCase):
    def upload(self, image, format="PNG", **options):
        stream = BytesIO()
        image.save(stream, format=format, **options)
        return SimpleUploadedFile("misleading.jpg", stream.getvalue(), content_type="image/jpeg")

    def test_avatar_dimensions_are_bounded_preserving_aspect_ratio(self):
        uploaded = self.upload(Image.new("RGB", (2400, 1200), "blue"))
        form = ProfileForm()
        form.cleaned_data = {"avatar": uploaded}
        result = form.clean_avatar()
        with Image.open(result) as image:
            self.assertEqual(image.size, (800, 400))
        self.assertLess(result.size, uploaded.size)

    def test_room_form_reencodes_and_discards_metadata_and_appended_bytes(self):
        metadata = PngImagePlugin.PngInfo()
        metadata.add_text("GPS", "private-location")
        uploaded = self.upload(Image.new("RGBA", (3000, 1500), (10, 20, 30, 70)), pnginfo=metadata)
        data = uploaded.read() + b"PRIVATE-APPENDED-CONTENT"
        form = ImageUploadForm({}, {"image": SimpleUploadedFile("claim.jpg", data)})
        self.assertTrue(form.is_valid(), form.errors)
        result = form.cleaned_data["image"]
        self.assertNotIn(b"PRIVATE-APPENDED-CONTENT", result.read())
        result.seek(0)
        with Image.open(result) as image:
            self.assertEqual(image.size, (2048, 1024))
            self.assertNotIn("GPS", image.info)
            actual = image.getpixel((0, 0))
            self.assertEqual(actual[3], 70)
            self.assertTrue(all(abs(left - right) <= 3 for left, right in zip(actual[:3], (10, 20, 30))))

    def test_exif_orientation_is_applied_before_resizing_and_not_retained(self):
        exif = Image.Exif()
        exif[274] = 6
        exif[270] = "private-description"
        uploaded = self.upload(Image.new("RGB", (1200, 600), "green"), format="JPEG", exif=exif)
        result = normalized_image(uploaded, max_edge=800)
        with Image.open(result) as image:
            self.assertEqual(image.size, (400, 800))
            self.assertFalse(image.getexif())

    def test_animated_png_is_rejected_instead_of_silently_losing_frames(self):
        uploaded = self.upload(Image.new("RGB", (10, 10), "red"), save_all=True,
                               append_images=[Image.new("RGB", (10, 10), "blue")], duration=100)
        with self.assertRaisesMessage(ValidationError, "ảnh tĩnh"):
            normalized_image(uploaded, max_edge=800)
