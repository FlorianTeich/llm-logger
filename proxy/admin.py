from django.contrib import admin

from .models import RequestLog


@admin.register(RequestLog)
class RequestLogAdmin(admin.ModelAdmin):
    list_display = (
        "started_at",
        "request_id",
        "endpoint",
        "model",
        "outcome",
        "status_code",
        "latency_ms",
        "total_tokens",
    )
    list_filter = ("outcome", "endpoint", "streaming", "started_at")
    search_fields = ("model", "error_message")
    readonly_fields = tuple(field.name for field in RequestLog._meta.fields)
    date_hierarchy = "started_at"
