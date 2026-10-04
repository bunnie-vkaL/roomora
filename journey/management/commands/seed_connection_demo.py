"""Populate the connection page with imported synthetic profiles on a local site."""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from core.models import Profile
from journey import models as m, services as s


class Command(BaseCommand):
    help = "Add local sample matches and incoming interests for one real account. DEBUG=True only."

    def add_arguments(self, parser):
        parser.add_argument("--user", required=True, help="Username of the account viewing the connection page.")
        parser.add_argument("--connected", type=int, default=2)
        parser.add_argument("--incoming", type=int, default=3)

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Connection demo data can only be added with DEBUG=True.")
        if not 0 <= options["connected"] <= 5 or not 0 <= options["incoming"] <= 5:
            raise CommandError("Choose between 0 and 5 profiles for each section.")
        actor = Profile.objects.filter(user__username=options["user"]).select_related("answers").first()
        if not actor or actor.is_synthetic or not actor.is_published or not actor.completed:
            raise CommandError("Choose a published, completed, non-synthetic account.")

        imported = list(Profile.objects.filter(sample_source__isnull=False, is_synthetic=True,
                                               is_published=True).select_related("answers", "sample_source"))
        imported_ids = {profile.pk for profile in imported}
        connected_ids = set()
        for connection in m.Connection.objects.filter(Q(low=actor) | Q(high=actor), active=True):
            other_id = connection.high_id if connection.low_id == actor.pk else connection.low_id
            if other_id in imported_ids:
                connected_ids.add(other_id)
        own_likes = set(m.SwipeDecision.objects.filter(actor=actor, choice=m.SwipeDecision.LIKE)
                        .values_list("target_id", flat=True))
        own_decisions = set(m.SwipeDecision.objects.filter(actor=actor).values_list("target_id", flat=True))
        incoming_ids = set(m.SwipeDecision.objects.filter(target=actor, actor_id__in=imported_ids,
                                                         choice=m.SwipeDecision.LIKE).values_list("actor_id", flat=True))

        ranked = []
        for profile in imported:
            if profile.pk in connected_ids:
                continue
            try:
                score = s.eligible_target(actor, profile).score
            except s.DomainError:
                continue
            ranked.append((profile, score))
        ranked.sort(key=lambda item: (item[0].pk not in own_likes, -item[1], item[0].pk))
        eligible_ids = {profile.pk for profile, _ in ranked}

        added_connected = []
        for profile, _ in ranked:
            if len(connected_ids) >= options["connected"]:
                break
            if profile.pk in incoming_ids or (profile.pk in own_decisions and profile.pk not in own_likes):
                continue
            if profile.pk not in own_likes:
                s.decide(actor, profile, m.SwipeDecision.LIKE)
            s.decide(profile, actor, m.SwipeDecision.LIKE)
            connected_ids.add(profile.pk)
            own_likes.add(profile.pk)
            own_decisions.add(profile.pk)
            added_connected.append(profile.name)

        pending_ids = (incoming_ids & eligible_ids) - connected_ids - own_likes
        added_incoming = []
        for profile, _ in ranked:
            if len(pending_ids) >= options["incoming"]:
                break
            if profile.pk in connected_ids or profile.pk in own_decisions or profile.pk in incoming_ids:
                continue
            s.decide(profile, actor, m.SwipeDecision.LIKE)
            pending_ids.add(profile.pk)
            added_incoming.append(profile.name)

        self.stdout.write(f"Account: {actor.user.username}")
        self.stdout.write(f"Connected: {len(connected_ids)} (+{len(added_connected)}): {', '.join(added_connected) or 'no new profiles'}")
        self.stdout.write(f"Incoming: {len(pending_ids)} (+{len(added_incoming)}): {', '.join(added_incoming) or 'no new profiles'}")
