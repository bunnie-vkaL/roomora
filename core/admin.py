from django.contrib import admin
from .models import (
    ConnectionRequest,
    LifestyleAnswers,
    PilotEvent,
    PilotExercise,
    Profile,
    Report,
)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("name", "user", "is_published", "is_synthetic", "updated_at")
    list_filter = ("is_published", "is_synthetic")
    search_fields = ("name", "user__email")


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["reporter", "target", "created_at", "resolved"]
    list_filter = ["resolved"]
    readonly_fields = ["reporter", "target", "reason", "created_at"]

    def has_add_permission(self, request):
        return False


admin.site.register([LifestyleAnswers, ConnectionRequest, PilotExercise, PilotEvent])
