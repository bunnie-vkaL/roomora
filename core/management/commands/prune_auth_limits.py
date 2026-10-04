from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import AuthRateBucket


class Command(BaseCommand):
    help = "Remove expired authentication and journey rate counters without touching accounts."

    def handle(self, **options):
        total, _ = AuthRateBucket.objects.filter(expires_at__lte=timezone.now()).delete()
        self.stdout.write(f"Removed {total} expired rate counters.")
