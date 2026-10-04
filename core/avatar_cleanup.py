"""Remove replaced local avatars only after their references commit."""
import logging
from pathlib import Path, PurePosixPath
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)


def queue_avatar_cleanup(name, storage, *, using="default"):
    if not name:
        return
    relative = PurePosixPath(name)
    if relative.is_absolute() or ".." in relative.parts or "\\" in name or ":" in name or relative.parts[0] != "avatars":
        return

    def remove_if_unused():
        from .models import Profile
        try:
            if Profile.objects.using(using).filter(avatar=name).exists():
                return
            # Only local files inside the public avatar directory are eligible.
            allowed = Path(settings.MEDIA_ROOT).resolve() / "avatars"
            target = Path(storage.path(name)).resolve()
            if not target.is_relative_to(allowed) or target == allowed:
                return
            storage.delete(name)
        except Exception:
            # A cleanup failure must not turn a committed upload into a reported failure.
            logger.warning("Unused avatar cleanup deferred; private operator review required.")

    transaction.on_commit(remove_if_unused, using=using)
