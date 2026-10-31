from django.contrib import admin

from .models import ModelRoute, RequestLog


@admin.register(ModelRoute)
class ModelRouteAdmin(admin.ModelAdmin):
    list_display = ("public_name", "upstream_name", "upstream_base_url", "updated_at")
    search_fields = ("public_name", "upstream_name", "upstream_base_url")
    ordering = ("public_name",)


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
