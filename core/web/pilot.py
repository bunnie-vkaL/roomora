"""Pilot study views, isolated from production discovery and account flows."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

from core.forms import PilotExerciseForm
from core.models import PilotEvent, PilotExercise


@login_required
def pilot_exercise(request):
    from core.web.legacy_discovery import find_matches

    profile = request.user.profile
    candidates = find_matches(profile)[:3]
    if not candidates:
        messages.info(request, "Cần có ít nhất một match để làm bài thử nghiệm.")
        return redirect("discover")
    exercise, _ = PilotExercise.objects.get_or_create(
        user=request.user,
        defaults={"score_first": bool(request.user.pk % 2), "candidate_ids": [person.pk for person, _ in candidates]},
    )
    candidates = [(person, result) for person, result in candidates if person.pk in exercise.candidate_ids]
    form = PilotExerciseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        lookup = {person.pk: person for person, _ in candidates}
        if form.cleaned_data["basic_choice"] not in lookup or form.cleaned_data["score_choice"] not in lookup:
            form.add_error(None, "Hãy chọn hồ sơ từ danh sách hiển thị.")
        else:
            exercise.basic_choice = lookup[form.cleaned_data["basic_choice"]]
            exercise.score_choice = lookup[form.cleaned_data["score_choice"]]
            exercise.basic_trust = form.cleaned_data["basic_trust"]
            exercise.score_trust = form.cleaned_data["score_trust"]
            exercise.feedback = form.cleaned_data["feedback"]
            exercise.completed_at = timezone.now()
            exercise.save()
            PilotEvent.objects.create(user=request.user, kind="pilot_completed")
            messages.success(request, "Cảm ơn bạn đã hoàn thành bài thử nghiệm.")
            return redirect("dashboard")
    return render(request, "core/pilot.html", {"form": form, "candidates": candidates, "exercise": exercise})


@user_passes_test(lambda user: user.is_staff)
def pilot_results(request):
    exercises = PilotExercise.objects.filter(completed_at__isnull=False)
    return render(request, "core/pilot_results.html", {"exercises": exercises, "event_counts": {
        kind: PilotEvent.objects.filter(kind=kind).count()
        for kind in ["profile_published", "comparison_view", "connection_invited", "connection_accept"]
    }})


@user_passes_test(lambda user: user.is_staff)
def pilot_export(request):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="roomora-pilot-results.csv"'
    writer = csv.writer(response)
    writer.writerow(["completed_at", "score_first", "basic_trust", "score_trust", "feedback"])
    for item in PilotExercise.objects.filter(completed_at__isnull=False):
        writer.writerow([item.completed_at, item.score_first, item.basic_trust, item.score_trust, item.feedback])
    return response
