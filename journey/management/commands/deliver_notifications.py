from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils import timezone
from journey.models import OutboxEvent
from journey.services import deliver_safely


class Command(BaseCommand):
    help = "Deliver retained in-app outbox events. Safe to retry."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        limit = options["limit"]
        if not 1 <= limit <= 500:
            raise CommandError("Limit must be between 1 and 500.")
        ids = list(OutboxEvent.objects.filter(delivered=False).filter(
            Q(retry_at__isnull=True) | Q(retry_at__lte=timezone.now())).order_by("pk").values_list("pk", flat=True)[:limit])
        delivered = sum(deliver_safely(event_id) for event_id in ids)
        self.stdout.write(f"Delivered {delivered}; retained {len(ids) - delivered} due events.")
        if delivered < len(ids):
            raise CommandError("Some events remain queued for retry.")
