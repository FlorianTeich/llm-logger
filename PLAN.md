# Implementation plan

## Goal

Build a self-hostable Django service that accepts OpenAI-compatible API requests, forwards them to configured LLM providers, and records the request, response, and operational outcome for later inspection.

## MVP scope and decisions

- Serve an OpenAI-compatible gateway at `/v1/models` and `/v1/chat/completions` first. Defer other OpenAI endpoints until this request path works end to end.
- Forward to an explicitly configured upstream base URL and API key. Keep credentials in environment-backed configuration; never persist or display authorization headers or provider secrets.
- Preserve compatible JSON bodies and upstream status codes/headers where safe. Support non-streaming first, then streaming without changing the client-facing SSE format.
- Record each accepted API request and its result, including request and response bodies, status, timing, usage, and failures. Make body capture, redaction, and retention configurable; document that prompts and completions may contain sensitive data.
- Use SQLite and Django ORM for local development. Use Django-authenticated HTML views for the request log, with the Django admin available for internal operations.

## MVP acceptance criteria

1. A client can point an OpenAI SDK at this service and make a chat completion request through it.
2. Each call to a supported `/v1` endpoint—including authentication, validation, upstream, and interrupted-stream failures—has a durable log entry with its outcome and available request/response content. Health checks and Django admin traffic are outside the LLM request log.
3. An authenticated operator can browse a paginated request list, filter/search it, and open a detail page to inspect one request and its response.

## Milestones and tasks

### 1. Project foundation — in progress

- [x] Initialize the repository as a Python project managed by `uv`.
- [x] Add the initial Django project layout and environment-based settings.
- [x] Resolve and lock dependencies.
- [x] Add pytest, pytest-django, and respx for automated tests and upstream mocking.
- [ ] Choose and configure formatting/lint tooling.

### 2. Provider configuration and access control

- [x] Define provider configuration (base URL, credential, timeout, allowed models) and validate required settings at startup.
- [x] Authenticate proxy callers with a configured API key using constant-time comparison; allow an explicit development-only open mode.
- [x] Define how incoming model names map to configured upstream models.
- [x] Protect operator pages with Django authentication and create/document the initial superuser flow.

### 3. OpenAI-compatible proxy/gateway

- [x] Implement `GET /v1/models`, returning configured models in the OpenAI response shape or forwarding the request to upstream `/models` when no model list is configured.
- [x] Implement `POST /v1/chat/completions` for non-streaming requests, forwarding compatible payloads and returning upstream response bodies/statuses.
- [x] Add request validation, upstream timeouts, connection error mapping, and OpenAI-shaped error responses.
- [x] Implement streaming responses and forward SSE events as they arrive; log upstream errors and client disconnects.
- [x] Add a local mock-upstream integration path so behavior can be exercised without provider credentials.

### 4. Request/result logging

- [x] Add a `RequestLog` model with a generated request ID, timestamps, endpoint/model, outcome state, HTTP status, latency, token usage, and error details. Log supported endpoint attempts even when auth, validation, or upstream handling fails.
- [x] Persist request and upstream result bodies/status for non-streaming requests; record failures even when the upstream cannot be reached.
- [x] Create a pending log before forwarding and finalize it with success/failure details. For streams, capture forwarded events and mark normal completion, upstream failure, or client disconnect.
- [x] Store only safe request metadata; never store authorization headers or provider credentials. Make body capture, JSON-field redaction, and size limits configurable.
- [x] Add indexes for timestamp, model, outcome/status, and request ID.
- [x] Add a retention/purge command with dry-run support.

### 5. Django request-log views

- [x] Build an authenticated, paginated request list showing time, request ID, model, status, latency, and token usage.
- [x] Add list filters for date range, model, status/outcome, and search by request ID/error text.
- [x] Build an authenticated request detail page that shows the stored request and response bodies, status, timing, usage, and any error in readable JSON/text form.
- [x] Ensure views escape displayed content and never render stored credentials or authorization headers.

### 6. Operations and data lifecycle

- [x] Add health/readiness endpoints.
- [ ] Add structured application logs.
- [x] Generate request correlation IDs and propagate them to upstream requests.
- [ ] Document retention, backup, and privacy behavior for logged prompts and completions.
- [x] Provide production database configuration, secret management notes, and Docker/deployment guidance.
- [x] Add usage documentation with OpenAI SDK and curl examples and supported compatibility details.

### 7. Verification and release readiness

- [x] Cover routing, auth, forwarding, error mapping, streaming, log persistence, retention purge, and list/detail views with automated tests.
- [ ] Review security, privacy, and operational failure modes before calling the MVP complete.

## Current task

The core proxy, request logging, authenticated list/detail pages, health/readiness endpoints, manual retention purge, and automated test suite are implemented. The initial migration is generated and applied locally. Production deployment now has Gunicorn, PostgreSQL, WhiteNoise static serving, Docker Compose, and deployment documentation. Remaining work includes formatting/lint tooling, structured application logs, and a final security/privacy review. Dependencies are managed by `uv` and locked in `uv.lock`.
