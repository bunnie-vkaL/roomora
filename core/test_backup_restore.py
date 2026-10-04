import json
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from django.test import SimpleTestCase
from core.backup_restore import build_snapshot, restore_snapshot, safe_destination


class BackupRestoreTests(SimpleTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.database = self.root / "source.sqlite3"
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute("CREATE TABLE accounts (name TEXT)")
            connection.execute("INSERT INTO accounts VALUES ('fixture')")
            connection.commit()
        self.media = self.root / "source-media"
        self.private = self.root / "source-private"
        for root in (self.media, self.private):
            (root / "nested").mkdir(parents=True)
        (self.media / "nested/avatar.webp").write_bytes(b"avatar fixture")
        (self.private / "nested/evidence.jpg").write_bytes(b"private fixture")
        self.backup = self.root / "snapshot"
        build_snapshot(self.database, self.media, self.private, self.backup)

    def test_restore_database_and_both_media_roots_without_changing_original(self):
        original = self.database.read_bytes()
        destination = self.root / "restore"
        restore_snapshot(self.backup, destination)
        with closing(sqlite3.connect(destination / "database.sqlite3")) as connection:
            self.assertEqual(connection.execute("SELECT name FROM accounts").fetchall(), [("fixture",)])
        self.assertEqual((destination / "media/nested/avatar.webp").read_bytes(), b"avatar fixture")
        self.assertEqual((destination / "private_media/nested/evidence.jpg").read_bytes(), b"private fixture")
        self.assertEqual(self.database.read_bytes(), original)
        with self.assertRaises(ValueError):
            restore_snapshot(self.backup, destination)

    def test_tampered_missing_and_extra_files_rejected_before_restore(self):
        media_file = self.backup / "media/nested/avatar.webp"
        for corruption in ("changed", "missing", "extra"):
            with self.subTest(corruption=corruption):
                if corruption == "changed":
                    media_file.write_bytes(b"tampered")
                elif corruption == "missing":
                    media_file.unlink()
                else:
                    media_file.write_bytes(b"avatar fixture")
                    (self.backup / "unexpected").write_bytes(b"extra")
                destination = self.root / ("restore-" + corruption)
                with self.assertRaises(ValueError):
                    restore_snapshot(self.backup, destination)
                self.assertFalse(destination.exists())

    def test_manifest_traversal_and_overlapping_destination_rejected(self):
        manifest_path = self.backup / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["files"]["../outside"] = "fake"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            restore_snapshot(self.backup, self.root / "restore")
        for destination in (self.media, self.media / "backup", self.root):
            with self.assertRaises(ValueError):
                safe_destination(destination, [self.media])
        self.assertEqual(safe_destination(self.root / "safe", [self.media]), self.root / "safe")

    def test_snapshot_does_not_overwrite_existing_directory(self):
        with self.assertRaises(ValueError):
            build_snapshot(self.database, self.media, self.private, self.backup)
        self.assertTrue((self.backup / "manifest.json").exists())
