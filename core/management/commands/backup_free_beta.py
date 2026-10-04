import uuid
import sqlite3
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from core.backup_restore import build_snapshot, safe_destination


class Command(BaseCommand):
    help = "Back up SQLite and both local media roots while all writers are stopped."

    def add_arguments(self, parser):
        parser.add_argument("--output-dir", required=True)
        parser.add_argument("--maintenance-confirmed", action="store_true")

    def handle(self, **options):
        database = settings.DATABASES["default"]
        if not options["maintenance_confirmed"]:
            raise CommandError("Stop web and management writers first; then use --maintenance-confirmed.")
        if database["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("This command supports SQLite only.")
        try:
            protected = [settings.BASE_DIR, settings.MEDIA_ROOT,
                settings.ROOMORA_PRIVATE_MEDIA_ROOT, Path(database["NAME"]).parent]
            if settings.STATIC_ROOT:
                protected.append(settings.STATIC_ROOT)
            output = safe_destination(options["output_dir"], protected)
            output.mkdir(parents=True, exist_ok=True, mode=0o700)
            snapshot = output / ("roomora-" + uuid.uuid4().hex)
            build_snapshot(database["NAME"], settings.MEDIA_ROOT, settings.ROOMORA_PRIVATE_MEDIA_ROOT, snapshot)
        except (ValueError, OSError, sqlite3.Error) as error:
            raise CommandError("Backup failed; inspect paths and available disk privately.") from error
        self.stdout.write(f"Verified snapshot: {snapshot}. Contains private data; keep outside public mappings.")
