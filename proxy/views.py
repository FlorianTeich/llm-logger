import json
import time
from typing import Iterator
from uuid import UUID

import httpx
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt

from .auth import proxy_key_is_valid
from .models import RequestLog


def _capture(raw: bytes) -> tuple[str, bool]:
    if not settings.REQUEST_LOG_STORE_BODIES:
        return "", False
    raw = _redact_payload(raw)
    limit = settings.REQUEST_LOG_MAX_BODY_BYTES
    truncated = limit > 0 and len(raw) > limit
    data = raw[:limit] if truncated else raw
    return data.decode("utf-8", errors="replace"), truncated


def _redact_payload(raw: bytes) -> bytes:
    if not settings.REQUEST_LOG_REDACT_FIELDS:
        return raw
    text = raw.decode("utf-8", errors="replace")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        # OpenAI streaming responses carry one JSON object per SSE data frame.
        lines = text.splitlines(keepends=True)
        redacted_lines = []
        for line in lines:
            if not line.startswith("data:"):
                redacted_lines.append(line)
                continue
            frame = line[5:].strip()
            try:
                value = json.loads(frame)
            except json.JSONDecodeError:
                redacted_lines.append(line)
                continue
            prefix = line[: len(line) - len(line.lstrip())] + "data: "
            ending = "\n" if line.endswith("\n") else ""
            redacted_lines.append(prefix + json.dumps(_redact_value(value), separators=(",", ":")) + ending)
        return "".join(redacted_lines).encode("utf-8")
    return json.dumps(_redact_value(payload), separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _redact_value(value):
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in settings.REQUEST_LOG_REDACT_FIELDS else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def _new_log(request: HttpRequest, endpoint: str) -> tuple[RequestLog, float, bytes]:
    started = time.monotonic()
    raw = request.body
    body, truncated = _capture(raw)
    log = RequestLog.objects.create(
        endpoint=endpoint,
        method=request.method[:12],
        request_body=body,
        request_body_truncated=truncated,
    )
    return log, started, raw


def _finalize(
    log: RequestLog,
    started: float,
    *,
    outcome: str,
    status_code: int,
    response_body: bytes = b"",
    usage_body: bytes | None = None,
    upstream_status_code: int | None = None,
    error_message: str = "",
) -> None:
    body, truncated = _capture(response_body)
    log.outcome = outcome
    log.status_code = status_code
    log.upstream_status_code = upstream_status_code
    log.latency_ms = max(0, int((time.monotonic() - started) * 1000))
    log.completed_at = timezone.now()
    log.response_body = body
    log.response_body_truncated = truncated
    log.error_message = error_message[:4000]
    usage = _usage_from_body((usage_body if usage_body is not None else response_body).decode("utf-8", errors="replace"))
    if usage:
        log.prompt_tokens = usage.get("prompt_tokens")
        log.completion_tokens = usage.get("completion_tokens")
        log.total_tokens = usage.get("total_tokens")
    log.save()


def _usage_from_body(body: str) -> dict[str, int] | None:
    candidates = [body]
    # Streaming responses contain JSON objects inside SSE data frames.
    candidates.extend(
        line[5:].strip()
        for line in body.splitlines()
        if line.startswith("data:") and line[5:].strip() != "[DONE]"
    )
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
        usage = payload.get("usage") if isinstance(payload, dict) else None
        if isinstance(usage, dict):
            return {
                key: usage[key]
                for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if isinstance(usage.get(key), int) and usage[key] >= 0
            }
    return None


def _error_response(
    log: RequestLog,
    started: float,
    *,
    message: str,
    status: int,
    error_type: str,
    code: str,
    outcome: str = RequestLog.Outcome.REJECTED,
    upstream_status: int | None = None,
    raw_body: bytes | None = None,
) -> JsonResponse:
    response_body = json.dumps(
        {"error": {"message": message, "type": error_type, "code": code}}
    ).encode()
    _finalize(
        log,
        started,
        outcome=outcome,
        status_code=status,
        upstream_status_code=upstream_status,
        response_body=raw_body if raw_body is not None else response_body,
        error_message=message,
    )
    response = JsonResponse(
        {"error": {"message": message, "type": error_type, "code": code}},
        status=status,
    )
    response["X-Request-ID"] = str(log.request_id)
    return response


def _authorized(request: HttpRequest, log: RequestLog, started: float) -> JsonResponse | None:
    if not settings.PROXY_API_KEY and not settings.DEBUG:
        return _error_response(
            log,
            started,
            message="Proxy authentication is not configured.",
            status=503,
            error_type="server_error",
            code="proxy_auth_not_configured",
            outcome=RequestLog.Outcome.FAILED,
        )
    if not proxy_key_is_valid(request):
        return _error_response(
            log,
            started,
            message="Invalid or missing API key.",
            status=401,
            error_type="authentication_error",
            code="invalid_api_key",
            outcome=RequestLog.Outcome.REJECTED,
        )
    return None


def _upstream_url(path: str) -> str:
    return f"{settings.UPSTREAM_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


def _upstream_headers(request_id: UUID, accept: str = "application/json") -> dict[str, str]:
    headers = {"Accept": accept, "X-Request-ID": str(request_id)}
    if settings.UPSTREAM_API_KEY:
        headers["Authorization"] = f"Bearer {settings.UPSTREAM_API_KEY}"
    return headers


def _response_headers(upstream_headers: httpx.Headers) -> dict[str, str]:
    allowed = {"content-type", "cache-control", "retry-after", "openai-processing-ms"}
    headers = {
        name: value
        for name, value in upstream_headers.items()
        if name.lower() in allowed or name.lower().startswith("openai-")
    }
    # The proxy may decode a compressed upstream body, so do not forward encoding or length.
    return headers


def _parse_payload(raw: bytes) -> dict | None:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _httpx_error(log: RequestLog, started: float, exc: httpx.HTTPError) -> JsonResponse:
    timed_out = isinstance(exc, httpx.TimeoutException)
    status = 504 if timed_out else 502
    code = "upstream_timeout" if timed_out else "upstream_connection_error"
    message = "The upstream provider timed out." if timed_out else "Could not reach the upstream provider."
    return _error_response(
        log,
        started,
        message=message,
        status=status,
        error_type="server_error",
        code=code,
        outcome=RequestLog.Outcome.FAILED,
    )


@csrf_exempt
def models_endpoint(request: HttpRequest) -> HttpResponse:
    log, started, _ = _new_log(request, "/v1/models")
    denied = _authorized(request, log, started)
    if denied:
        return denied
    if request.method != "GET":
        return _error_response(
            log,
            started,
            message="This endpoint only supports GET.",
            status=405,
            error_type="invalid_request_error",
            code="method_not_allowed",
        )

    configured = settings.UPSTREAM_MODELS or list(settings.UPSTREAM_MODEL_MAP.keys())
    if configured:
        body = json.dumps(
            {
                "object": "list",
                "data": [
                    {"id": model, "object": "model", "created": 0, "owned_by": "proxy"}
                    for model in configured
                ],
            }
        ).encode()
        _finalize(log, started, outcome=RequestLog.Outcome.SUCCEEDED, status_code=200, response_body=body)
        response = HttpResponse(body, content_type="application/json")
        response["X-Request-ID"] = str(log.request_id)
        return response

    try:
        with httpx.Client(timeout=settings.UPSTREAM_TIMEOUT_SECONDS) as client:
            upstream = client.get(
                _upstream_url("models"), headers=_upstream_headers(log.request_id)
            )
    except httpx.HTTPError as exc:
        return _httpx_error(log, started, exc)

    raw = upstream.content
    outcome = (
        RequestLog.Outcome.SUCCEEDED
        if upstream.is_success
        else RequestLog.Outcome.FAILED
    )
    _finalize(
        log,
        started,
        outcome=outcome,
        status_code=upstream.status_code,
        upstream_status_code=upstream.status_code,
        response_body=raw,
        error_message="" if upstream.is_success else f"Upstream returned HTTP {upstream.status_code}.",
    )
    response = HttpResponse(raw, status=upstream.status_code)
    for name, value in _response_headers(upstream.headers).items():
        response[name] = value
    response["X-Request-ID"] = str(log.request_id)
    return response


@csrf_exempt
def chat_completions(request: HttpRequest) -> HttpResponse:
    log, started, raw = _new_log(request, "/v1/chat/completions")
    denied = _authorized(request, log, started)
    if denied:
        return denied
    if request.method != "POST":
        return _error_response(
            log,
            started,
            message="This endpoint only supports POST.",
            status=405,
            error_type="invalid_request_error",
            code="method_not_allowed",
        )

    payload = _parse_payload(raw)
    if payload is None:
        return _error_response(
            log,
            started,
            message="Request body must be a JSON object.",
            status=400,
            error_type="invalid_request_error",
            code="invalid_json",
        )

    model = payload.get("model")
    log.model = model[:255] if isinstance(model, str) else ""
    configured_models = settings.UPSTREAM_MODELS or list(settings.UPSTREAM_MODEL_MAP.keys())
    if not isinstance(model, str) or not model.strip():
        log.save(update_fields=("model",))
        return _error_response(
            log,
            started,
            message="A model name is required.",
            status=400,
            error_type="invalid_request_error",
            code="missing_model",
        )
    if configured_models and model not in configured_models:
        log.save(update_fields=("model",))
        return _error_response(
            log,
            started,
            message=f"Model '{model}' is not configured on this proxy.",
            status=404,
            error_type="invalid_request_error",
            code="model_not_found",
        )

    if not isinstance(payload.get("messages"), list):
        log.save(update_fields=("model",))
        return _error_response(
            log,
            started,
            message="The messages field must be an array.",
            status=400,
            error_type="invalid_request_error",
            code="invalid_messages",
        )
    if "stream" in payload and not isinstance(payload["stream"], bool):
        log.save(update_fields=("model",))
        return _error_response(
            log,
            started,
            message="The stream field must be a boolean.",
            status=400,
            error_type="invalid_request_error",
            code="invalid_stream_option",
        )

    streaming = payload.get("stream") is True
    log.streaming = streaming
    log.save(update_fields=("model", "streaming"))
    upstream_payload = dict(payload)
    upstream_model = settings.UPSTREAM_MODEL_MAP.get(model, model)
    upstream_payload["model"] = upstream_model
    upstream_body = json.dumps(upstream_payload, separators=(",", ":")).encode()
    headers = _upstream_headers(
        log.request_id,
        "text/event-stream" if streaming else "application/json",
    )
    headers["Content-Type"] = "application/json"

    if streaming:
        return _stream_chat(log, started, upstream_body, headers)
    return _buffered_chat(log, started, upstream_body, headers)


def _buffered_chat(
    log: RequestLog, started: float, body: bytes, headers: dict[str, str]
) -> HttpResponse:
    try:
        with httpx.Client(timeout=settings.UPSTREAM_TIMEOUT_SECONDS) as client:
            upstream = client.post(
                _upstream_url("chat/completions"), content=body, headers=headers
            )
    except httpx.HTTPError as exc:
        return _httpx_error(log, started, exc)

    raw = upstream.content
    success = upstream.is_success
    _finalize(
        log,
        started,
        outcome=RequestLog.Outcome.SUCCEEDED if success else RequestLog.Outcome.FAILED,
        status_code=upstream.status_code,
        upstream_status_code=upstream.status_code,
        response_body=raw,
        error_message="" if success else f"Upstream returned HTTP {upstream.status_code}.",
    )
    response = HttpResponse(raw, status=upstream.status_code)
    for name, value in _response_headers(upstream.headers).items():
        response[name] = value
    response["X-Request-ID"] = str(log.request_id)
    return response


def _stream_chat(
    log: RequestLog, started: float, body: bytes, headers: dict[str, str]
) -> HttpResponse:
    client = httpx.Client(timeout=settings.UPSTREAM_TIMEOUT_SECONDS)
    try:
        upstream_request = client.build_request(
            "POST", _upstream_url("chat/completions"), content=body, headers=headers
        )
        upstream = client.send(upstream_request, stream=True)
    except httpx.HTTPError as exc:
        client.close()
        return _httpx_error(log, started, exc)

    def stream_body() -> Iterator[bytes]:
        chunks: list[bytes] = []
        usage_tail = bytearray()
        completed = False
        stream_error = ""
        try:
            for chunk in upstream.iter_bytes():
                usage_tail.extend(chunk)
                if len(usage_tail) > 65536:
                    del usage_tail[:-65536]
                if settings.REQUEST_LOG_STORE_BODIES:
                    chunks.append(chunk)
                yield chunk
            completed = True
        except httpx.HTTPError as exc:
            stream_error = f"Upstream stream failed: {exc.__class__.__name__}."
        finally:
            raw = b"".join(chunks)
            if completed:
                outcome = (
                    RequestLog.Outcome.SUCCEEDED
                    if upstream.is_success
                    else RequestLog.Outcome.FAILED
                )
            else:
                outcome = RequestLog.Outcome.INTERRUPTED
                if not stream_error:
                    stream_error = "Stream ended before completion (client disconnected or stream closed)."
            _finalize(
                log,
                started,
                outcome=outcome,
                status_code=upstream.status_code,
                upstream_status_code=upstream.status_code,
                response_body=raw,
                usage_body=raw if settings.REQUEST_LOG_STORE_BODIES else bytes(usage_tail),
                error_message=stream_error
                or ("" if upstream.is_success else f"Upstream returned HTTP {upstream.status_code}."),
            )
            upstream.close()
            client.close()

    response = StreamingHttpResponse(
        stream_body(),
        status=upstream.status_code,
        content_type=upstream.headers.get("content-type", "text/event-stream"),
    )
    for name, value in _response_headers(upstream.headers).items():
        if name.lower() != "content-type":
            response[name] = value
    response["X-Request-ID"] = str(log.request_id)
    return response


@login_required
def request_log_list(request: HttpRequest) -> HttpResponse:
    logs = RequestLog.objects.all()
    model = request.GET.get("model", "").strip()
    outcome = request.GET.get("outcome", "").strip()
    from_date = parse_date(request.GET.get("from", ""))
    to_date = parse_date(request.GET.get("to", ""))
    search = request.GET.get("q", "").strip()
    if model:
        logs = logs.filter(model__icontains=model)
    if outcome in RequestLog.Outcome.values:
        logs = logs.filter(outcome=outcome)
    if from_date:
        logs = logs.filter(started_at__date__gte=from_date)
    if to_date:
        logs = logs.filter(started_at__date__lte=to_date)
    if search:
        search_filter = Q(error_message__icontains=search)
        try:
            search_filter |= Q(request_id=UUID(search))
        except ValueError:
            search_filter |= Q(model__icontains=search)
        logs = logs.filter(search_filter)

    page_obj = Paginator(logs, 50).get_page(request.GET.get("page"))
    return render(
        request,
        "proxy/request_log_list.html",
        {
            "page_obj": page_obj,
            "filters": {
                "model": model,
                "outcome": outcome,
                "from": request.GET.get("from", ""),
                "to": request.GET.get("to", ""),
                "q": search,
            },
            "outcomes": RequestLog.Outcome.choices,
            "query_string": _query_without_page(request),
        },
    )


@login_required
def request_log_detail(request: HttpRequest, request_id: UUID) -> HttpResponse:
    log = get_object_or_404(RequestLog, request_id=request_id)
    return render(
        request,
        "proxy/request_log_detail.html",
        {
            "log": log,
            "request_pretty": _pretty_body(log.request_body),
            "response_pretty": _pretty_body(log.response_body),
        },
    )


def _pretty_body(body: str) -> str:
    try:
        return json.dumps(json.loads(body), indent=2, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        return body


def health(request: HttpRequest) -> JsonResponse:
    return JsonResponse({"status": "ok"})


def readiness(request: HttpRequest) -> JsonResponse:
    try:
        connection.ensure_connection()
    except DatabaseError:
        return JsonResponse({"status": "not_ready", "database": "unavailable"}, status=503)
    return JsonResponse({"status": "ready", "database": "ok"})


def _query_without_page(request: HttpRequest) -> str:
    query = request.GET.copy()
    query.pop("page", None)
    return query.urlencode()
