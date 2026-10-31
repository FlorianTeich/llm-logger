from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from proxy.models import RequestLog


pytestmark = pytest.mark.django_db


def create_log(**kwargs):
    defaults = {
        "endpoint": "/v1/chat/completions",
        "method": "POST",
        "model": "test-model",
        "outcome": RequestLog.Outcome.SUCCEEDED,
        "status_code": 200,
        "request_body": '{"model":"test-model","messages":[]}',
        "response_body": '{"choices":[],"usage":{"total_tokens":0}}',
    }
    defaults.update(kwargs)
    return RequestLog.objects.create(**defaults)


def test_log_pages_require_login_and_show_request_details(client):
    log = create_log()
    assert client.get("/logs/").status_code == 302

    user = get_user_model().objects.create_user(username="operator", password="Good-Password-482!")
    client.force_login(user)
    listing = client.get("/logs/")
    detail = client.get(f"/logs/{log.request_id}/")

    assert listing.status_code == 200
    assert str(log.request_id) in listing.content.decode()
    assert detail.status_code == 200
    assert "test-model" in detail.content.decode()
    assert "choices" in detail.content.decode()


def test_log_list_filters_by_model_and_outcome(client):
    user = get_user_model().objects.create_user(username="operator", password="Good-Password-482!")
    client.force_login(user)
    matching = create_log(model="alpha", outcome=RequestLog.Outcome.SUCCEEDED)
    create_log(model="beta", outcome=RequestLog.Outcome.FAILED)

    response = client.get("/logs/?model=alpha&outcome=succeeded")
    content = response.content.decode()

    assert response.status_code == 200
    assert str(matching.request_id) in content
    assert "beta" not in content


def test_purge_command_supports_dry_run_and_deletes_old_logs():
    old_log = create_log()
    old_log.started_at = timezone.now() - timedelta(days=120)
    old_log.save(update_fields=("started_at",))
    recent_log = create_log()
    output = StringIO()

    call_command("purge_request_logs", days=90, dry_run=True, stdout=output)
    assert "Would delete 1" in output.getvalue()
    assert RequestLog.objects.filter(pk=old_log.pk).exists()

    call_command("purge_request_logs", days=90, stdout=StringIO())
    assert not RequestLog.objects.filter(pk=old_log.pk).exists()
    assert RequestLog.objects.filter(pk=recent_log.pk).exists()


def test_health_and_readiness_endpoints(client):
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/readyz").json() == {"status": "ready", "database": "ok"}
