from django.contrib import admin
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["reporter", "target", "created_at", "resolved"]
    list_filter = ["resolved"]
    readonly_fields = ["reporter", "target", "reason", "created_at"]

    def has_add_permission(self, request):
        return False
