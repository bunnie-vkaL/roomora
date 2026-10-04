"""Offline SQLite + local media snapshots. Never overwrite a restore target."""
import hashlib
import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def files(root):
    if root.is_symlink():
        raise ValueError("Symbolic links are not supported.")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Symbolic links are not supported.")
        if path.is_file():
            yield path


def integrity(path):
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("SQLite integrity check failed.")


def private_copy(source, target):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
    target.chmod(0o600)


def build_snapshot(database, media, private_media, destination):
    sources = [Path(value).absolute() for value in (database, media, private_media)]
    database, media, private_media = sources
    if database.is_symlink() or not database.is_file():
        raise ValueError("A regular SQLite database is required.")
    if destination.exists():
        raise ValueError("Destination already exists.")
    destination.mkdir(mode=0o700)
    try:
        target_db = destination / "database.sqlite3"
        target_db.touch(mode=0o600, exist_ok=False)
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as source:
            with closing(sqlite3.connect(target_db)) as target:
                source.backup(target)
        integrity(target_db)
        for label, root in (("media", media), ("private_media", private_media)):
            (destination / label).mkdir(mode=0o700)
            if root.is_symlink():
                raise ValueError("Symbolic links are not supported.")
            if root.exists():
                for path in files(root):
                    private_copy(path, destination / label / path.relative_to(root))
        entries = {path.relative_to(destination).as_posix(): digest(path) for path in files(destination)}
        manifest = {"format": 1, "requires_offline_writes": True, "files": entries}
        manifest_path = destination / "manifest.json"
        with manifest_path.open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
        manifest_path.chmod(0o600)
    except Exception:
        shutil.rmtree(destination)
        raise


def restore_snapshot(backup, destination):
    if backup.is_symlink() or destination.exists():
        raise ValueError("Backup must be regular and destination must not exist.")
    if (backup / "manifest.json").is_symlink():
        raise ValueError("Symbolic links are not supported.")
    manifest = json.loads((backup / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Invalid backup manifest.")
    entries = manifest.get("files")
    if manifest.get("format") != 1 or not isinstance(entries, dict) or "database.sqlite3" not in entries:
        raise ValueError("Invalid backup manifest.")
    actual = {path.relative_to(backup).as_posix() for path in files(backup)} - {"manifest.json"}
    if actual != set(entries):
        raise ValueError("Backup file inventory mismatch.")
    for name, expected in entries.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name:
            raise ValueError("Invalid backup path.")
        if name != "database.sqlite3" and relative.parts[0] not in ("media", "private_media"):
            raise ValueError("Unexpected backup file.")
        if digest(backup / relative) != expected:
            raise ValueError("Backup checksum mismatch.")
    integrity(backup / "database.sqlite3")
    destination.mkdir(mode=0o700)
    try:
        for name in entries:
            private_copy(backup / name, destination / name)
        for label in ("media", "private_media"):
            (destination / label).mkdir(exist_ok=True, mode=0o700)
        integrity(destination / "database.sqlite3")
    except Exception:
        shutil.rmtree(destination)
        raise


def safe_destination(value, protected):
    destination = Path(value).expanduser().resolve()
    for root in protected:
        root = Path(root).resolve()
        if destination == root or destination.is_relative_to(root) or root.is_relative_to(destination):
            raise ValueError("Destination overlaps an application or public directory.")
    return destination
