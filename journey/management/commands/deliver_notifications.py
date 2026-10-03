from django.core.management.base import BaseCommand
from journey.models import OutboxEvent
from journey.services import deliver_event


class Command(BaseCommand):
    help = "Deliver retained in-app outbox events. Safe to retry."

    def handle(self, *args, **options):
        delivered = 0
        for event_id in OutboxEvent.objects.filter(delivered=False).values_list("pk", flat=True):
            deliver_event(event_id)
            delivered += 1
        self.stdout.write(f"Delivered {delivered} events")
