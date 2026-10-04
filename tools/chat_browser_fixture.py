"""Disposable localhost browser fixture; never reads the application's user DB."""
import argparse
import os
from pathlib import Path
import sys
import uuid

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
from django.conf import settings


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--action", choices=["serve", "serve-existing", "candidates", "rooms", "reply", "disconnect"], required=True)
    options = parser.parse_args()
    root = Path(options.root).resolve()
    allowed = BASE.parent / "private-fixtures"
    if not root.is_relative_to(allowed.resolve()) or root == allowed.resolve():
        raise ValueError("Fixture must be inside the private-fixtures workspace directory.")
    root.mkdir(parents=True, exist_ok=True)
    settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": root / "fixture.sqlite3",
        "OPTIONS": {"timeout": 20, "transaction_mode": "IMMEDIATE"}}}
    settings.MEDIA_ROOT = root / "media"
    settings.ROOMORA_PRIVATE_MEDIA_ROOT = root / "private_media"
    settings.SESSION_COOKIE_NAME = "roomora_browser_fixture_session"
    settings.CSRF_COOKIE_NAME = "roomora_browser_fixture_csrf"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.DEBUG = True
    import django
    django.setup()
    from django.contrib.auth.models import User
    from django.core.management import call_command
    from core.constants import QUESTIONS
    from core.models import Profile, LifestyleAnswers
    from journey import services as service, models
    if options.action == "serve-existing":
        if not (root / "fixture.sqlite3").exists() or not User.objects.filter(username="browser-0@example.invalid").exists():
            raise ValueError("An existing browser fixture is required.")
        call_command("runserver", "127.0.0.1:8010", use_reloader=False)
        return
    if options.action == "candidates":
        for index, name in enumerate(("Hà · hồ sơ thử", "Minh · hồ sơ thử", "Vy · hồ sơ thử"), start=2):
            email = f"browser-{index}@example.invalid"
            user, created = User.objects.get_or_create(username=email, defaults={"email": email, "password": "!"})
            if created:
                person = Profile.objects.create(user=user, name=name, age=22 + index, areas=["Cầu Giấy"],
                    rent_min=3000000, rent_max=5000000, contact_type="zalo", contact_value="", is_published=True)
                LifestyleAnswers.objects.create(profile=person, values={key: 0 for key, *_ in QUESTIONS})
        print("Added only fictional candidates to the isolated fixture.")
        return
    if options.action == "rooms":
        actor = Profile.objects.get(user__username="browser-0@example.invalid")
        other = Profile.objects.get(user__username="browser-1@example.invalid")
        conversation = models.Conversation.objects.get()
        workspace = service.invite_workspace(actor, conversation.pk, "An & Bình · bảng nhà thử")
        if workspace.status == "pending":
            service.respond_workspace(other, workspace.pk, True)
        samples = (
            ("Studio gần trường · căn mẫu", [("Thuê", "monthly", "known", 4200000), ("Cọc", "deposit", "known", 4200000), ("Dọn vào", "initial", "estimated", 600000)]),
            ("Căn sáng ở Cầu Giấy · căn mẫu", [("Thuê", "monthly", "known", 3600000), ("Điện nước", "monthly", "unknown", None), ("Cọc", "deposit", "unknown", None), ("Khoản một lần", "initial", "known", 0)]),
            ("Căn cần hỏi thêm · căn mẫu", []),
        )
        for title, costs in samples:
            room, created = models.RoomOption.objects.get_or_create(owner=actor, workspace=None, title=title,
                defaults={"area": "Cầu Giấy", "notes": "Dữ liệu minh họa cục bộ, không phải tin cho thuê thực tế."})
            if created:
                for label, period, state, amount in costs:
                    models.RoomCost.objects.create(room=room, label=label, period=period, state=state, amount=amount,
                        source="Thông tin minh họa" if amount is not None else "")
            if title == samples[0][0]:
                service.share_room(actor, room.pk, workspace.pk)
        print("Added only fictional rentals to the isolated fixture.")
        return
    if options.action == "serve":
        if (root / "fixture.sqlite3").exists():
            raise ValueError("Use a fresh fixture directory; never overwrite an existing fixture.")
        call_command("migrate", verbosity=0, interactive=False)
        profiles = []
        for index, name in enumerate(("An · tài khoản thử", "Bình · tài khoản thử")):
            email = f"browser-{index}@example.invalid"
            user = User.objects.create_user(email, email, "Local-fixture-2026!")
            profile = Profile.objects.create(user=user, name=name, age=25, areas=["Cầu Giấy"],
                rent_min=3000000, rent_max=5000000, contact_type="zalo", contact_value="", is_published=True)
            LifestyleAnswers.objects.create(profile=profile, values={key: 0 for key, *_ in QUESTIONS})
            profiles.append(profile)
        service.decide(profiles[0], profiles[1], "like")
        conversation = service.decide(profiles[1], profiles[0], "like")
        service.send_message(profiles[1], conversation.pk, "Chào An, đây là tin nhắn thử trong dữ liệu tách biệt.", uuid.uuid4())
        print(f"Fixture chat: http://127.0.0.1:8010/together/chat/{conversation.pk}/", flush=True)
        call_command("runserver", "127.0.0.1:8010", use_reloader=False)
    else:
        actor = Profile.objects.get(user__username="browser-1@example.invalid")
        conversation = models.Conversation.objects.select_related("connection").get()
        if options.action == "reply":
            service.send_message(actor, conversation.pk, "Tin mới từ Bình: cùng kiểm tra ngân sách và khu vực nhé.", uuid.uuid4())
        else:
            service.disconnect(actor, conversation.connection_id)
        print("Updated only the isolated fixture.")


if __name__ == "__main__":
    main()
