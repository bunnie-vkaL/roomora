"""Actor-level room-image budget, checked inside the serialized mutation."""
from django.conf import settings
from .models import RoomImage
from .services import DomainError


def check_room_image_budget(actor, uploaded):
    count_limit = getattr(settings, "ROOMORA_PERSON_IMAGE_COUNT", 0)
    byte_limit = getattr(settings, "ROOMORA_PERSON_IMAGE_BYTES", 0)
    if not count_limit and not byte_limit:
        return
    images = RoomImage.objects.filter(creator=actor).only("image")
    if count_limit:
        images = images[:count_limit]
    images = list(images)
    if count_limit and len(images) >= count_limit:
        raise DomainError(f"Bạn đã đạt giới hạn {count_limit} ảnh trọ của bản thử nghiệm. Các ảnh đã lưu vẫn được giữ.", 409)
    if byte_limit:
        try:
            total = sum(image.image.size for image in images)
        except (OSError, ValueError):
            raise DomainError("Chưa thể kiểm tra dung lượng ảnh đã lưu. Vui lòng thử lại sau.", 503)
        if total + uploaded.size > byte_limit:
            raise DomainError(f"Ảnh mới vượt hạn mức {byte_limit // (1024 * 1024)} MB ảnh trọ của bạn. Hãy chọn ảnh nhẹ hơn; các ảnh đã lưu vẫn được giữ.", 409)
