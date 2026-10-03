"""Three explicitly synthetic accounts for local, manual journey verification."""
from datetime import date, time

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.constants import QUESTIONS
from core.models import LifestyleAnswers, Profile
from journey.models import LivingPreferences


class Command(BaseCommand):
    help = "Create three labeled local demo accounts, never modify real accounts. DEBUG=True only."

    def add_arguments(self, parser):
        parser.add_argument("--password", required=True, help="Password for synthetic local accounts only.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo accounts can only be created with DEBUG=True.")
        if len(options["password"]) < 12:
            raise CommandError("Use a local demo password of at least 12 characters.")
        for suffix, name, sleep in (("an", "Mẫu thử · An", time(23)), ("binh", "Mẫu thử · Bình", time(0)), ("chi", "Mẫu thử · Chi", time(22))):
            email = f"journey-demo-{suffix}@roomora.local"
            existing = User.objects.filter(username=email).first()
            if existing and (not hasattr(existing, "profile") or not existing.profile.is_synthetic):
                raise CommandError(f"Refusing to modify an account not marked synthetic: {email}")
            user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
            user.set_password(options["password"])
            user.save()
            profile, _ = Profile.objects.get_or_create(user=user, defaults={
                "name": name, "age": 25, "birth_year": 2001, "areas": ["Cầu Giấy"], "rent_min": 2500000,
                "rent_max": 4500000, "contact_type": "zalo", "contact_value": "Dữ liệu mẫu", "is_synthetic": True, "is_published": True,
            })
            LifestyleAnswers.objects.get_or_create(profile=profile, defaults={"values": {key: 0 for key, *_ in QUESTIONS}})
            LivingPreferences.objects.get_or_create(profile=profile, defaults={
                "move_in_from": date(2026, 11, 1), "move_in_until": date(2026, 11, 15),
                "needs": "Cần bàn làm việc và chỗ để xe; đây là nhu cầu mẫu.", "sleep_at": sleep, "wake_at": time(7),
                "quiet_from": time(22), "quiet_until": time(7), "total_monthly_budget": 4000000, "upfront_budget": 15000000,
            })
            self.stdout.write(f"Local synthetic account: {email} (profile {profile.pk})")
        self.stdout.write(self.style.SUCCESS("Demo data ready. Use only in a local database; do not deploy this database."))
