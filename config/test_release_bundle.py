import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

from django.test import SimpleTestCase

from deploy.free_beta import load_environment
from tools.build_free_beta_bundle import REQUIRED_FILES, build_bundle, verify_bundle


class ReleaseBundleTests(SimpleTestCase):
    def make_source(self, root):
        source = root / "source"
        for directory in ("config", "core", "journey", "deploy", "static", "templates"):
            (source / directory).mkdir(parents=True)
        for name in REQUIRED_FILES:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("local-working-copy-content", encoding="utf-8")
        return source

    def test_archive_keeps_local_code_and_excludes_private_runtime_data(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = self.make_source(root)
            for name in (".env", "roomora.sqlite3", "media/avatars/private.png", "private_media/room.png",
                         "core/fixtures/users.json", "core/tests.py", "core/management/commands/seed_demo.py",
                         "config/.env", "config/test_settings.py", "static/private.txt"):
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("PRIVATE-CONTENT-MUST-NOT-SHIP", encoding="utf-8")
            output = root / "release.zip"
            manifest = build_bundle(source, output)
            self.assertFalse(manifest["public_deployed"])
            self.assertEqual(set(manifest["files"]), set(REQUIRED_FILES))
            with zipfile.ZipFile(output) as archive:
                self.assertEqual(archive.read("roomora/core/models.py"), b"local-working-copy-content")
                for name in archive.namelist():
                    self.assertNotIn(b"PRIVATE-CONTENT-MUST-NOT-SHIP", archive.read(name))
            self.assertEqual(manifest["files"]["core/models.py"]["sha256"], hashlib.sha256(b"local-working-copy-content").hexdigest())

    def test_missing_source_and_existing_release_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = self.make_source(root)
            output = root / "release.zip"
            output.write_bytes(b"KEEP-THIS-RELEASE")
            with self.assertRaises(FileExistsError):
                build_bundle(source, output)
            self.assertEqual(output.read_bytes(), b"KEEP-THIS-RELEASE")
            (source / "core/models.py").unlink()
            with self.assertRaises(ValueError):
                build_bundle(source, root / "missing.zip")
            self.assertFalse((root / "missing.zip").exists())

    def test_verifier_rejects_changed_file_even_with_valid_zip_crc(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = self.make_source(root)
            output = root / "release.zip"
            build_bundle(source, output)
            changed = root / "changed.zip"
            with zipfile.ZipFile(output) as original, zipfile.ZipFile(changed, "w") as tampered:
                for name in original.namelist():
                    tampered.writestr(name, b"changed" if name.endswith("models.py") else original.read(name))
            with self.assertRaises(ValueError):
                verify_bundle(changed)


class PrivateEnvironmentTests(SimpleTestCase):
    def write_environment(self, root, overrides=None):
        values = {"SECRET_KEY": "TEST-ONLY-SECRET", "ALLOWED_HOSTS": "example.invalid",
                  "CSRF_TRUSTED_ORIGINS": "https://example.invalid", "DEFAULT_FROM_EMAIL": "test@example.invalid",
                  "BREVO_API_KEY": "TEST-ONLY-NO-DELIVERY"}
        values.update({key: str(root / key.lower()) for key in
                       ("STATIC_ROOT", "MEDIA_ROOT", "ROOMORA_PRIVATE_MEDIA_ROOT", "ROOMORA_DATA_ROOT")})
        values.update(overrides or {})
        path = root / "private-env.json"
        path.write_text(json.dumps(values), encoding="utf-8")
        path.chmod(0o600)
        return path

    def test_loader_selects_free_profile_and_rejects_public_location_or_unknown_keys(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {}, clear=False):
            root = Path(folder)
            load_environment(self.write_environment(root))
            self.assertEqual(os.environ["DJANGO_SETTINGS_MODULE"], "config.free_beta_settings")
            self.assertEqual(os.environ["ROOMORA_TRUST_PROXY_PROTO"], "0")
            before = dict(os.environ)
            for overrides in ({"MEDIA_ROOT": str(root)}, {"PATH": "unexpected"}, {"BREVO_API_KEY": 42}):
                with self.assertRaises(ValueError):
                    load_environment(self.write_environment(root, overrides))
                self.assertEqual(dict(os.environ), before)

    def test_cli_config_error_does_not_print_file_contents(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "private-env.json"
            path.write_text('{"secret": "PRIVATE-TEST-MARKER", invalid', encoding="utf-8")
            path.chmod(0o600)
            script = Path(__file__).resolve().parents[1] / "deploy/free_beta.py"
            result = subprocess.run([sys.executable, str(script), "--env", str(path), "check"], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertNotIn("PRIVATE-TEST-MARKER", result.stdout + result.stderr)
            self.assertIn("Private configuration could not be loaded", result.stderr)
