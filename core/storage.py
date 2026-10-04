"""Single-host upload budget shared by public and private filesystem storage."""
import os
from pathlib import Path
import shutil
import stat
from django.conf import settings
from django.core.files import locks
from django.core.files.storage import FileSystemStorage


class UploadCapacityError(Exception):
    message = "Hiện chưa thể lưu thêm ảnh. Vui lòng thử lại sau; bạn vẫn có thể dùng các tính năng khác."


def used_bytes(roots):
    total = 0
    for root in roots:
        if root.is_symlink():
            raise UploadCapacityError()
        if not root.exists():
            continue
        for path in root.rglob("*"):
            info = path.lstat()
            if stat.S_ISREG(info.st_mode):
                total += info.st_size
            elif not stat.S_ISDIR(info.st_mode):
                raise UploadCapacityError()
    return total


class BudgetFileSystemStorage(FileSystemStorage):
    def _save(self, name, content):
        budget = getattr(settings, "ROOMORA_UPLOAD_BUDGET_BYTES", 0)
        if not budget:
            return super()._save(name, content)
        lock_root = Path(settings.ROOMORA_DATA_ROOT)
        roots = [Path(settings.MEDIA_ROOT), Path(settings.ROOMORA_PRIVATE_MEDIA_ROOT)]
        try:
            lock_root.mkdir(parents=True, exist_ok=True, mode=0o700)
            descriptor = os.open(lock_root / "upload-budget.lock", os.O_CREAT | os.O_RDWR, 0o600)
            with os.fdopen(descriptor, "r+b") as lock_file:
                if not locks.lock(lock_file, locks.LOCK_EX | locks.LOCK_NB):
                    raise UploadCapacityError()
                try:
                    size = content.size
                    if type(size) is not int or size < 0 or used_bytes(roots) + size > budget:
                        raise UploadCapacityError()
                    # Check each filesystem in case upload roots live on separate volumes.
                    for root in roots:
                        parent = root
                        while not parent.exists():
                            parent = parent.parent
                        if shutil.disk_usage(parent).free - size < settings.ROOMORA_UPLOAD_FREE_RESERVE_BYTES:
                            raise UploadCapacityError()
                    return super()._save(name, content)
                finally:
                    locks.unlock(lock_file)
        except OSError as error:
            raise UploadCapacityError() from error
