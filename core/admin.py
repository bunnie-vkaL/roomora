from django.contrib import admin
from .models import ConnectionRequest, LifestyleAnswers, PilotEvent, PilotExercise, Profile


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "is_published", "is_synthetic", "updated_at")
    list_filter = ("is_published", "is_synthetic")
    search_fields = ("name", "user__email")

admin.site.register([LifestyleAnswers, ConnectionRequest, PilotExercise, PilotEvent])
