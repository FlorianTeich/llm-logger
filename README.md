# LLM Log N Map

An OpenAI-compatible LLM proxy built with Django. It forwards chat completion requests to a configured upstream provider, logs request/response outcomes, and provides authenticated pages for browsing those logs.

## Development

This project uses [uv](https://docs.astral.sh/uv/) for Python and dependency management.

Set environment variables before starting the app. The Django settings read them from the process environment; no `.env` file is loaded automatically.

```sh
export DJANGO_SECRET_KEY='replace-for-any-non-local-deployment'
export UPSTREAM_BASE_URL='https://api.openai.com/v1'
export UPSTREAM_API_KEY='your-upstream-key'
export PROXY_API_KEY='your-client-facing-proxy-key'
export UPSTREAM_MODELS='gpt-4o-mini'

uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Run the automated test suite with `uv run pytest`.

Point an OpenAI SDK at `http://localhost:8000/v1` and use `PROXY_API_KEY` as its API key. The proxy supports `GET /v1/models` and `POST /v1/chat/completions`, including streaming chat completions. If `UPSTREAM_MODELS` is empty, `/v1/models` is forwarded to the upstream provider. Set `UPSTREAM_MODEL_MAP` to a JSON object to map public model names to upstream names, for example `'{"my-model":"provider-model-v2"}'`.

Example request:

```sh
curl http://localhost:8000/v1/chat/completions -H "Authorization: Bearer $PROXY_API_KEY" -H "Content-Type: application/json" -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Hello"}]}'
```

Python SDK example (install the `openai` client separately):

```python
import os
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key=os.environ["PROXY_API_KEY"],
)
result = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[{"role": "user", "content": "Hello"}],
)
print(result.choices[0].message.content)
```

`/logs/` lists requests and supports filtering by model, outcome, date, and request ID/error text. Select a request to view its details. Sign in with a Django user; `/admin/` is available for administration.

Request and response body logging is on by default. `REQUEST_LOG_STORE_BODIES=false` disables body capture while keeping request metadata. `REQUEST_LOG_MAX_BODY_BYTES` limits each captured body (`0` means unlimited). `REQUEST_LOG_REDACT_FIELDS` is a comma-separated list of JSON keys to redact; it defaults to common credential field names. Authorization headers are never stored. `REQUEST_LOG_RETENTION_DAYS` defaults to 90 days; logs are not deleted automatically. Preview the purge with `uv run python manage.py purge_request_logs --dry-run`, then run `uv run python manage.py purge_request_logs` to apply the configured retention period. Configure `UPSTREAM_TIMEOUT_SECONDS` to change the upstream timeout. When `DEBUG=true` and no `PROXY_API_KEY` is set, proxy API-key authentication is open for local development; production must set a key.

`/healthz` is a liveness endpoint and `/readyz` checks database connectivity.

See [PLAN.md](PLAN.md) for the roadmap and remaining work. The initial implementation covers models and chat completions; other OpenAI endpoints, multi-provider routing, and production deployment hardening remain future work.
