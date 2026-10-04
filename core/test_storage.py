from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
import tempfile
from unittest.mock import patch
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image
from core.storage import BudgetFileSystemStorage, UploadCapacityError, used_bytes
from core.tests import profile
from journey.models import PrivateStorage


class UploadBudgetTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.media, self.private, self.data = root / "media", root / "private", root / "data"
        self.override = override_settings(MEDIA_ROOT=self.media, ROOMORA_PRIVATE_MEDIA_ROOT=self.private,
            ROOMORA_DATA_ROOT=self.data, ROOMORA_UPLOAD_BUDGET_BYTES=10, ROOMORA_UPLOAD_FREE_RESERVE_BYTES=0)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_public_and_private_share_budget_and_rejection_does_not_write(self):
        public = BudgetFileSystemStorage()
        private = PrivateStorage()
        public.save("first", ContentFile(b"123456"))
        private.save("second", ContentFile(b"1234"))
        with self.assertRaises(UploadCapacityError):
            public.save("rejected", ContentFile(b"x"))
        self.assertFalse((self.media / "rejected").exists())
        self.assertEqual(used_bytes([self.media, self.private]), 10)
        private.delete("second")
        public.save("after-delete", ContentFile(b"1234"))

    def test_concurrent_writes_cannot_overcommit_shared_budget(self):
        def upload(index):
            storage = BudgetFileSystemStorage()
            try:
                storage.save(f"file-{index}", ContentFile(b"123456"))
                return True
            except UploadCapacityError:
                return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(upload, range(16)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(used_bytes([self.media, self.private]), 6)

    def test_low_disk_or_unavailable_lock_fails_closed(self):
        storage = BudgetFileSystemStorage()
        with override_settings(ROOMORA_UPLOAD_FREE_RESERVE_BYTES=100), patch("core.storage.shutil.disk_usage") as disk:
            disk.return_value.free = 100
            with self.assertRaises(UploadCapacityError):
                storage.save("low-disk", ContentFile(b"x"))
        with patch("core.storage.locks.lock", return_value=False):
            with self.assertRaises(UploadCapacityError):
                storage.save("busy", ContentFile(b"x"))
        self.assertEqual(used_bytes([self.media, self.private]), 0)


class DirectAvatarUploadTests(TestCase):
    def setUp(self):
        self.actor = profile("upload-budget@test.com")
        self.client.force_login(self.actor.user)

    def test_fake_image_rejected_by_direct_endpoint(self):
        response = self.client.post(reverse("upload_avatar"), {"avatar": SimpleUploadedFile("photo.png", b"<html>fake</html>", content_type="image/png")}, secure=True)
        self.assertEqual(response.status_code, 400)
        self.actor.refresh_from_db()
        self.assertFalse(self.actor.avatar)

    def test_direct_endpoint_normalizes_and_handles_capacity_without_changing_record(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with override_settings(MEDIA_ROOT=root / "media", ROOMORA_PRIVATE_MEDIA_ROOT=root / "private",
                ROOMORA_DATA_ROOT=root / "data", ROOMORA_UPLOAD_BUDGET_BYTES=100000,
                ROOMORA_UPLOAD_FREE_RESERVE_BYTES=0,
                STORAGES={"default": {"BACKEND": "core.storage.BudgetFileSystemStorage"},
                          "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}):
                def upload():
                    stream = BytesIO()
                    Image.new("RGB", (1200, 600), "blue").save(stream, format="PNG")
                    return SimpleUploadedFile("claim.jpg", stream.getvalue() + b"PRIVATE-TRAILER", content_type="image/jpeg")
                response = self.client.post(reverse("upload_avatar"), {"avatar": upload()}, secure=True)
                self.assertEqual(response.status_code, 200)
                self.actor.refresh_from_db()
                original_name = self.actor.avatar.name
                with self.actor.avatar.open("rb") as stored:
                    self.assertNotIn(b"PRIVATE-TRAILER", stored.read())
                    stored.seek(0)
                    with Image.open(stored) as image:
                        self.assertEqual(image.size, (800, 400))
                with override_settings(ROOMORA_UPLOAD_BUDGET_BYTES=1):
                    response = self.client.post(reverse("upload_avatar"), {"avatar": upload()}, secure=True)
                    self.assertEqual(response.status_code, 503)
                self.actor.refresh_from_db()
                self.assertEqual(self.actor.avatar.name, original_name)
                self.assertTrue(self.actor.avatar.storage.exists(original_name))


class AvatarCleanupTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.override = override_settings(MEDIA_ROOT=self.root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.actor = profile("avatar-cleanup@test.com")
        self.client.force_login(self.actor.user)
        self.actor.avatar.save("old.png", ContentFile(b"old-avatar-fixture"))
        self.old_name = self.actor.avatar.name
        self.storage = self.actor.avatar.storage

    def test_replacement_and_explicit_removal_delete_only_after_commit(self):
        stream = BytesIO()
        Image.new("RGB", (10, 10), "blue").save(stream, format="PNG")
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("upload_avatar"), {"avatar": SimpleUploadedFile("new.png", stream.getvalue())}, secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(self.storage.exists(self.old_name))
        self.assertFalse(self.storage.exists(self.old_name))
        self.actor.refresh_from_db()
        new_name = self.actor.avatar.name
        self.assertTrue(self.storage.exists(new_name))
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("delete_avatar"), secure=True)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(self.storage.exists(new_name))
        self.assertFalse(self.storage.exists(new_name))
        self.actor.refresh_from_db()
        self.assertFalse(self.actor.avatar)

    def test_shared_reference_and_rolled_back_removal_keep_file(self):
        from django.db import transaction
        from core.avatar_cleanup import queue_avatar_cleanup
        other = profile("shared-avatar@test.com", avatar=self.old_name)
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse("delete_avatar"), secure=True)
        self.assertTrue(self.storage.exists(self.old_name))
        self.actor.avatar = self.old_name
        self.actor.save(update_fields=["avatar"])
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    other.avatar = None
                    other.save(update_fields=["avatar"])
                    self.actor.avatar = None
                    self.actor.save(update_fields=["avatar"])
                    queue_avatar_cleanup(self.old_name, self.storage)
                    raise ValueError("rollback fixture")
            except ValueError:
                pass
        self.assertTrue(self.storage.exists(self.old_name))
        self.actor.refresh_from_db()
        self.assertEqual(self.actor.avatar.name, self.old_name)

    def test_unsafe_paths_are_ignored_and_cleanup_failure_does_not_fail_commit(self):
        from core.avatar_cleanup import queue_avatar_cleanup
        with patch.object(self.storage, "delete") as delete:
            with self.captureOnCommitCallbacks(execute=True):
                for name in ("../outside", "private/evidence.png", "avatars/../../outside", "avatars\\outside"):
                    queue_avatar_cleanup(name, self.storage)
            delete.assert_not_called()
        self.actor.avatar = None
        self.actor.save(update_fields=["avatar"])
        with patch.object(self.storage, "delete", side_effect=OSError("PRIVATE-PATH")):
            with self.assertLogs("core.avatar_cleanup", level="WARNING") as logs:
                with self.captureOnCommitCallbacks(execute=True):
                    queue_avatar_cleanup(self.old_name, self.storage)
            self.assertNotIn("PRIVATE-PATH", "\n".join(logs.output))
        self.assertTrue(self.storage.exists(self.old_name))
