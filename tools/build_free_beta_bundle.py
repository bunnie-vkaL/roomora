"""Package current runtime source only; never copy local databases or uploads."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[1]
CODE_DIRS = ("config", "core", "journey", "deploy")
ASSET_SUFFIXES = {".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff2"}
EXTRA_FILES = ("manage.py", "requirements.txt", "docs/free-beta.md", "docs/free-account-start.vi.md",
               "docs/pythonanywhere-release.vi.md", "deploy/free-beta.env.example", "deploy/pythonanywhere_wsgi.py.example")
REQUIRED_FILES = ("manage.py", "requirements.txt", "config/free_beta_settings.py", "core/models.py",
                  "journey/models.py", "templates/base.html", "static/design.css", "deploy/free_beta.py")
EXCLUDED_CODE = {"tests.py", "test_settings.py", "seed_demo.py", "seed_journey_demo.py", "import_sample_profiles.py"}
MAX_SOURCE_BYTES = 16 * 1024 * 1024


def runtime_files(source):
    source = Path(source).resolve()
    selected = set()
    for directory in (*CODE_DIRS, "static", "templates"):
        folder = source / directory
        if not folder.is_dir() or folder.is_symlink():
            raise ValueError("Runtime directory is missing or linked.")
        for path in folder.rglob("*"):
            relative = path.relative_to(source)
            if any(part.startswith(".") or part == "__pycache__" for part in relative.parts):
                continue
            if path.is_symlink():
                raise ValueError("Runtime tree contains a symbolic link.")
            if not path.is_file():
                continue
            if directory in CODE_DIRS:
                include = path.suffix == ".py" and path.name not in EXCLUDED_CODE and not path.name.startswith("test_")
            elif directory == "templates":
                include = path.suffix == ".html"
            else:
                include = path.suffix.lower() in ASSET_SUFFIXES
            if include:
                selected.add(relative)
    for name in EXTRA_FILES:
        path = source / name
        if path.is_symlink():
            raise ValueError("Release support file is linked.")
        if path.is_file():
            selected.add(Path(name))
    if any(Path(name) not in selected for name in REQUIRED_FILES):
        raise ValueError("Required runtime source is missing.")
    return sorted(selected, key=lambda path: path.as_posix())


def build_bundle(source, output):
    source, output = Path(source).resolve(), Path(output).absolute()
    files = runtime_files(source)
    payloads, total = {}, 0
    for relative in files:
        path = source / relative
        if path.is_symlink() or not path.resolve().is_relative_to(source):
            raise ValueError("Runtime file escaped the source tree.")
        payload = path.read_bytes()
        total += len(payload)
        if total > MAX_SOURCE_BYTES:
            raise ValueError("Runtime source exceeds the reviewable release size.")
        payloads[relative.as_posix()] = payload
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=source, capture_output=True, text=True)
    manifest = {"format": 1, "source": "current local runtime files, including uncommitted changes",
                "base_git_head": revision.stdout.strip() if revision.returncode == 0 else None,
                "public_deployed": False, "raw_source_bytes": total,
                "files": {name: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                          for name, data in payloads.items()},
                "excluded": [".git", ".env and private configuration", "DB and sessions", "uploads and backups",
                             "fixtures and imported datasets", "virtualenv", "tests and demo/import commands"],
                "limits": "File inventory and hashes are not a comprehensive secret audit or a digital signature."}
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create: never overwrite another release, including a partially built one.
    with output.open("xb") as stream, zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in payloads.items():
            archive.writestr("roomora/" + name, data)
        archive.writestr("roomora/release-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    verify_bundle(output)
    return manifest


def verify_bundle(path):
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise ValueError("Release archive is duplicated or corrupt.")
        manifest = json.loads(archive.read("roomora/release-manifest.json"))
        expected = {"roomora/" + name for name in manifest["files"]} | {"roomora/release-manifest.json"}
        if set(names) != expected:
            raise ValueError("Release inventory does not match its manifest.")
        for name, record in manifest["files"].items():
            parts = Path(name).parts
            if not parts or Path(name).is_absolute() or any(part in ("..", ".") for part in parts) or "\\" in name or ":" in name:
                raise ValueError("Unsafe release path.")
            payload = archive.read("roomora/" + name)
            if len(payload) != record["bytes"] or hashlib.sha256(payload).hexdigest() != record["sha256"]:
                raise ValueError("Release file does not match its recorded hash.")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    options = parser.parse_args()
    result = build_bundle(ROOT, options.output)
    print(json.dumps({"files": len(result["files"]), "raw_source_bytes": result["raw_source_bytes"],
                      "archive_verified": True, "public_deployed": False}))
