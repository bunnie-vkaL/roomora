"""Isolated local measurement; synthetic fixtures do not validate match quality."""
import argparse
import json
import os
from pathlib import Path
import random
import statistics
import sys
import tempfile
import time
import tracemalloc

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"
from django.conf import settings


def run(output):
    with tempfile.TemporaryDirectory(prefix="roomora-benchmark-") as directory:
        settings.DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(Path(directory) / "fixture.sqlite3")}}
        settings.DEBUG = False
        import django
        django.setup()
        from django.contrib.auth.models import User
        from django.core.management import call_command
        from django.db import connection, connections
        from django.test.utils import CaptureQueriesContext
        from core.constants import QUESTIONS
        from core.models import Profile, LifestyleAnswers
        from journey.views import candidate_rows, candidate_card
        call_command("migrate", verbosity=0, interactive=False)
        randomizer = random.Random(20261004)
        measurements = []
        try:
            for count in (50, 250, 1000):
                existing = User.objects.count()
                User.objects.bulk_create([User(username=f"benchmark-{index}", password="!") for index in range(existing, count + 1)])
                user_ids = User.objects.filter(profile__isnull=True).values_list("pk", flat=True)
                Profile.objects.bulk_create([Profile(user_id=pk, name=f"Fixture {pk}", age=25, areas=["Cầu Giấy"],
                    rent_min=3000000, rent_max=5000000, contact_type="zalo", contact_value="", is_published=True) for pk in user_ids])
                answers = []
                for pk in Profile.objects.filter(answers__isnull=True).values_list("pk", flat=True):
                    values = {key: randomizer.randrange(min(2, len(options))) for key, _, _, options in QUESTIONS}
                    values["D2"] = 0
                    values["D3"] = 0
                    answers.append(LifestyleAnswers(profile_id=pk, values=values))
                LifestyleAnswers.objects.bulk_create(answers)
                actor = Profile.objects.select_related("answers").order_by("pk").first()
                full = candidate_rows(actor)
                compact = candidate_rows(actor, build_cards=False)
                assert [(row["profile"].pk, row["score"]) for row in full] == [(row["profile"].pk, row["score"]) for row in compact]
                expanded = [candidate_card(actor, row["profile"], row["result"], saved=row["saved"]) for row in compact[:10]]
                assert expanded == full[:10]
                for mode in ("all_cards", "visible_page_only"):
                    def operation():
                        rows = candidate_rows(actor, build_cards=mode == "all_cards")
                        if mode == "visible_page_only":
                            [candidate_card(actor, row["profile"], row["result"], saved=row["saved"]) for row in rows[:10]]
                        return rows
                    durations = []
                    for _ in range(7):
                        start = time.perf_counter()
                        with CaptureQueriesContext(connection) as queries:
                            rows = operation()
                        durations.append((time.perf_counter() - start) * 1000)
                        assert len(queries) == 4
                    tracemalloc.start()
                    rows = operation()
                    _, peak = tracemalloc.get_traced_memory()
                    tracemalloc.stop()
                    measurements.append({"pool_size": count, "eligible_count": len(rows), "mode": mode,
                        "query_count": 4, "samples": 7, "median_ms": round(statistics.median(durations), 2),
                        "max_sample_ms": round(max(durations), 2), "peak_python_allocated_bytes": peak})
        finally:
            connections.close_all()
        result = {"scope": "single-process local SQLite synthetic candidate service; excludes HTTP/render/proxy/concurrent load",
                  "production_database_touched": False, "ranking_and_visible_cards_identical": True,
                  "match_quality_validated": False, "measurements": measurements}
        Path(output).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    run(parser.parse_args().output)
