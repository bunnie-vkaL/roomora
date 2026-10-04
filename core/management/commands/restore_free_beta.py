from pathlib import Path
import sqlite3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from core.backup_restore import restore_snapshot, safe_destination


class Command(BaseCommand):
    help = "Verify and restore a snapshot into a NEW isolated directory; never replaces live data."

    def add_arguments(self, parser):
        parser.add_argument("--backup", required=True)
        parser.add_argument("--destination", required=True)

    def handle(self, **options):
        try:
            backup = Path(options["backup"]).absolute()
            protected = [settings.BASE_DIR, settings.MEDIA_ROOT, settings.ROOMORA_PRIVATE_MEDIA_ROOT,
                Path(settings.DATABASES["default"]["NAME"]).parent, backup]
            if settings.STATIC_ROOT:
                protected.append(settings.STATIC_ROOT)
            destination = safe_destination(options["destination"], protected)
            restore_snapshot(backup, destination)
        except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
            raise CommandError("Restore rejected; verify backup inventory, checksums and isolated destination.") from error
        self.stdout.write(f"Verified isolated restore: {destination}. Live settings and data were not replaced.")
