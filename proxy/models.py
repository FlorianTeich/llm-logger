import uuid

from django.db import models


class RequestLog(models.Model):
    class Outcome(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        REJECTED = "rejected", "Rejected"
        INTERRUPTED = "interrupted", "Interrupted"

    request_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    endpoint = models.CharField(max_length=100, db_index=True)
    method = models.CharField(max_length=12)
    model = models.CharField(max_length=255, blank=True, db_index=True)
    outcome = models.CharField(
        max_length=16, choices=Outcome.choices, default=Outcome.PENDING, db_index=True
    )
    status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    upstream_status_code = models.PositiveSmallIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    streaming = models.BooleanField(default=False)
    request_body = models.TextField(blank=True)
    response_body = models.TextField(blank=True)
    request_body_truncated = models.BooleanField(default=False)
    response_body_truncated = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    prompt_tokens = models.PositiveIntegerField(null=True, blank=True)
    completion_tokens = models.PositiveIntegerField(null=True, blank=True)
    total_tokens = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at",)
        indexes = [models.Index(fields=("started_at", "outcome"))]

    def __str__(self) -> str:
        return f"{self.request_id} {self.method} {self.endpoint} [{self.outcome}]"
