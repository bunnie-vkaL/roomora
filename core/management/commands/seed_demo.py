import random
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from core.constants import QUESTIONS
from core.models import LifestyleAnswers, Profile
from core.scoring import SCORING_VERSION


class Command(BaseCommand):
    help = "Create 40 clearly labeled synthetic ROOMORA profiles for development."

    def handle(self, *args, **options):
        random.seed(20261001)
        archetypes = [
            ("Cầu Giấy", 3_000_000, [1, 0, 1, 1, 1, 1, 0, 1, 0, 0, 0, 1, 1, 1, 1, 0]),
            ("Đống Đa", 3_500_000, [2, 1, 2, 2, 2, 1, 1, 1, 1, 0, 1, 2, 1, 2, 2, 1]),
            ("Thanh Xuân", 2_500_000, [0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0]),
            ("Tây Hồ", 4_000_000, [3, 2, 2, 2, 2, 2, 1, 2, 1, 0, 2, 2, 2, 3, 3, 2]),
        ]
        for number in range(1, 41):
            district, rent_min, anchor = archetypes[(number - 1) // 10]
            email = f"synthetic-{number:02d}@roomora.local"
            user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
            user.set_unusable_password(); user.save()
            profile, _ = Profile.objects.get_or_create(user=user, defaults={
                "name": f"Mẫu thử {number:02d}", "age": random.randint(22, 35), "gender": "",
                "areas": [district], "rent_min": rent_min,
                "rent_max": rent_min + 2_000_000, "contact_type": "zalo", "contact_value": "Dữ liệu giả",
                "is_published": True, "is_synthetic": True,
            })
            profile.areas = [district]
            profile.rent_min = rent_min
            profile.rent_max = rent_min + 2_000_000
            values = {key: anchor[index] for index, (key, _, _, _) in enumerate(QUESTIONS)}
            # A small soft-preference change creates useful score variation
            # without making most demo profiles fail hard gates.
            varied_key = random.choice(["C2", "C3", "D4", "D5", "E1", "F2"])
            varied_index = next(i for i, (key, _, _, _) in enumerate(QUESTIONS) if key == varied_key)
            option_count = len(QUESTIONS[varied_index][3])
            values[varied_key] = max(0, min(option_count - 1, values[varied_key] + random.choice([-1, 1])))
            LifestyleAnswers.objects.update_or_create(profile=profile, defaults={"values": values})
            profile.is_published = True
            profile.questionnaire_version = SCORING_VERSION
            profile.save(update_fields=["areas", "rent_min", "rent_max", "is_published", "questionnaire_version"])
        self.stdout.write(self.style.SUCCESS("Created or refreshed 40 synthetic profiles. They are labeled as demo data locally and excluded when DEBUG=False."))
