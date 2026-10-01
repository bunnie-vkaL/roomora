import random
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from core.constants import AREAS, QUESTIONS
from core.models import LifestyleAnswers, Profile


class Command(BaseCommand):
    help = "Create 40 clearly labeled synthetic ROOMORA profiles for development."

    def handle(self, *args, **options):
        random.seed(20261001)
        for number in range(1, 41):
            email = f"synthetic-{number:02d}@roomora.local"
            user, _ = User.objects.get_or_create(username=email, defaults={"email": email})
            user.set_unusable_password(); user.save()
            profile, _ = Profile.objects.get_or_create(user=user, defaults={
                "name": f"Mẫu thử {number:02d}", "age": random.randint(22, 35), "gender": "",
                "areas": random.sample(AREAS, random.randint(1, 3)), "rent_min": random.choice([2500000, 3000000, 3500000, 4000000]),
                "rent_max": random.choice([4500000, 5000000, 5500000, 6000000]), "contact_type": "zalo", "contact_value": "Dữ liệu giả",
                "is_published": True, "is_synthetic": True,
            })
            if profile.rent_min > profile.rent_max:
                profile.rent_max = profile.rent_min + 1000000; profile.save()
            values = {key: random.randrange(len(options)) for key, _, _, options in QUESTIONS}
            LifestyleAnswers.objects.update_or_create(profile=profile, defaults={"values": values})
        self.stdout.write(self.style.SUCCESS("Created or refreshed 40 synthetic profiles. They are labeled as demo data locally and excluded when DEBUG=False."))
