import json

import httpx
import pytest
import respx
from django.test import Client

from proxy.models import RequestLog


pytestmark = pytest.mark.django_db


def test_models_returns_configured_models_and_logs_request(settings, auth_headers):
    settings.UPSTREAM_MODELS = ["fast-model", "quality-model"]

    response = Client().get("/v1/models", **auth_headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["data"]] == [
        "fast-model",
        "quality-model",
    ]
    log = RequestLog.objects.get()
    assert log.endpoint == "/v1/models"
    assert log.outcome == RequestLog.Outcome.SUCCEEDED
    assert log.status_code == 200
    assert response["X-Request-ID"] == str(log.request_id)


def test_models_forwards_to_upstream_when_no_models_are_configured(auth_headers):
    upstream_payload = {"object": "list", "data": [{"id": "remote-model"}]}
    with respx.mock(assert_all_called=True) as router:
        route = router.get("https://upstream.test/v1/models").mock(
            return_value=httpx.Response(200, json=upstream_payload)
        )
        response = Client().get("/v1/models", **auth_headers)

    assert response.status_code == 200
    assert response.json() == upstream_payload
    assert route.calls.last.request.headers["Authorization"] == "Bearer test-upstream-key"
    log = RequestLog.objects.get()
    assert log.upstream_status_code == 200
    assert json.loads(log.response_body) == upstream_payload


def test_chat_completion_forwards_request_and_logs_usage_and_redacted_body(
    settings, auth_headers
):
    settings.UPSTREAM_MODELS = ["public-model"]
    settings.UPSTREAM_MODEL_MAP = {"public-model": "provider-model"}
    upstream_payload = {
        "id": "completion-1",
        "object": "chat.completion",
        "choices": [{"message": {"role": "assistant", "content": "Hello"}}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
    }
    request_body = {
        "model": "public-model",
        "messages": [{"role": "user", "content": "Hi"}],
        "api_key": "body-secret",
    }
    with respx.mock(assert_all_called=True) as router:
        route = router.post("https://upstream.test/v1/chat/completions").mock(
            return_value=httpx.Response(
                201,
                json=upstream_payload,
                headers={"OpenAI-Processing-Ms": "12"},
            )
        )
        response = Client().post(
            "/v1/chat/completions",
            data=json.dumps(request_body),
            content_type="application/json",
            **auth_headers,
        )

    assert response.status_code == 201
    assert response.json() == upstream_payload
    assert response["OpenAI-Processing-Ms"] == "12"
    sent = json.loads(route.calls.last.request.content)
    assert sent["model"] == "provider-model"
    assert sent["messages"] == request_body["messages"]
    assert route.calls.last.request.headers["Authorization"] == "Bearer test-upstream-key"
    log = RequestLog.objects.get()
    assert log.outcome == RequestLog.Outcome.SUCCEEDED
    assert log.status_code == log.upstream_status_code == 201
    assert log.model == "public-model"
    assert log.prompt_tokens == 3
    assert log.completion_tokens == 2
    assert log.total_tokens == 5
    assert json.loads(log.request_body)["api_key"] == "[REDACTED]"
    assert route.calls.last.request.headers["X-Request-ID"] == str(log.request_id)


def test_upstream_error_is_returned_and_logged(auth_headers):
    error_body = {"error": {"message": "model overloaded", "type": "server_error"}}
    with respx.mock(assert_all_called=True) as router:
        router.post("https://upstream.test/v1/chat/completions").mock(
            return_value=httpx.Response(503, json=error_body)
        )
        response = Client().post(
            "/v1/chat/completions",
            data=json.dumps({"model": "m1", "messages": []}),
            content_type="application/json",
            **auth_headers,
        )

    assert response.status_code == 503
    assert response.json() == error_body
    log = RequestLog.objects.get()
    assert log.outcome == RequestLog.Outcome.FAILED
    assert log.status_code == log.upstream_status_code == 503
    assert "503" in log.error_message


def test_invalid_auth_is_logged_and_never_forwarded():
    with respx.mock(assert_all_called=False) as router:
        route = router.post("https://upstream.test/v1/chat/completions")
        response = Client().post(
            "/v1/chat/completions",
            data=json.dumps({"model": "m1", "messages": []}),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrong-key",
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
    assert route.call_count == 0
    log = RequestLog.objects.get()
    assert log.outcome == RequestLog.Outcome.REJECTED
    assert log.status_code == 401
    assert "wrong-key" not in log.request_body


@pytest.mark.parametrize(
    ("body", "expected_code"),
    [
        (b"not json", "invalid_json"),
        (b'{"messages":[]}', "missing_model"),
        (b'{"model":"m1","messages":"hello"}', "invalid_messages"),
        (b'{"model":"m1","messages":[],"stream":"yes"}', "invalid_stream_option"),
    ],
)
def test_invalid_request_is_returned_and_logged(body, expected_code, auth_headers):
    response = Client().post(
        "/v1/chat/completions",
        data=body,
        content_type="application/json",
        **auth_headers,
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == expected_code
    log = RequestLog.objects.get()
    assert log.outcome == RequestLog.Outcome.REJECTED
    assert log.status_code == 400


def test_streaming_response_is_forwarded_and_logged(auth_headers):
    event_1 = 'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n'
    event_2 = 'data: {"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":1,"total_tokens":3}}\n\n'
    events = (event_1 + event_2 + "data: [DONE]\n\n").encode()
    with respx.mock(assert_all_called=True) as router:
        router.post("https://upstream.test/v1/chat/completions").mock(
            return_value=httpx.Response(
                200, content=events, headers={"Content-Type": "text/event-stream"}
            )
        )
        response = Client().post(
            "/v1/chat/completions",
            data=json.dumps(
                {"model": "m1", "messages": [{"role": "user", "content": "Hi"}], "stream": True}
            ),
            content_type="application/json",
            **auth_headers,
        )
        streamed = b"".join(response.streaming_content)

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/event-stream")
    assert streamed == events
    log = RequestLog.objects.get()
    assert log.streaming is True
    assert log.outcome == RequestLog.Outcome.SUCCEEDED
    assert log.response_body == events.decode()
    assert log.total_tokens == 3


def test_upstream_timeout_returns_gateway_timeout_and_logs_failure(auth_headers):
    with respx.mock(assert_all_called=True) as router:
        router.post("https://upstream.test/v1/chat/completions").mock(
            side_effect=httpx.ReadTimeout("late")
        )
        response = Client().post(
            "/v1/chat/completions",
            data=json.dumps({"model": "m1", "messages": []}),
            content_type="application/json",
            **auth_headers,
        )

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "upstream_timeout"
    assert RequestLog.objects.get().outcome == RequestLog.Outcome.FAILED
