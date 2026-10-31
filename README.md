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

## Production deployment with Docker Compose

The included Compose setup runs Gunicorn and PostgreSQL, persists database data in a named volume, and serves collected static files through WhiteNoise. It binds the app to `127.0.0.1` on the host so a TLS reverse proxy can sit in front of it.

1. Copy `.env.example` to `.env`, set strong unique values for `DJANGO_SECRET_KEY`, `POSTGRES_PASSWORD`, `PROXY_API_KEY`, and `UPSTREAM_API_KEY`, and set the real public hostname in `DJANGO_ALLOWED_HOSTS` and `DJANGO_CSRF_TRUSTED_ORIGINS`. Keep `.env` out of source control. You can generate secrets with `openssl rand -base64 48`.
2. Build and start the services: `docker compose up -d --build`.
3. Apply database migrations: `docker compose exec web uv run --no-sync python manage.py migrate`.
4. Create an operator account: `docker compose exec web uv run --no-sync python manage.py createsuperuser`.
5. Configure a reverse proxy with HTTPS to `127.0.0.1:8000` and have it set `X-Forwarded-Proto: https` for TLS requests. The example enables `DJANGO_SECURE_PROXY_SSL_HEADER` and `DJANGO_SECURE_SSL_REDIRECT`; use those settings only when the app can be reached through a trusted proxy that overwrites that header. Optionally configure HSTS after confirming the entire hostname is HTTPS. Keep the app port private to the host or trusted proxy.

For a non-Docker WSGI deployment, install dependencies with `uv sync --no-dev --frozen`, set `DJANGO_DEBUG=false`, a secret key, allowed hosts, and PostgreSQL settings (`DB_HOST`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`), then run `uv run python manage.py migrate`, `uv run python manage.py collectstatic --noinput`, and `uv run gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 125`. Use a process manager and terminate HTTPS at a trusted proxy. Alternatively, `DATABASE_URL` accepts PostgreSQL URLs and SQLite URLs.

Back up PostgreSQL independently of the container and verify restores. Request logs may contain prompts and completions; body capture is disabled in `.env.example`, and retention cleanup remains a scheduled operator task (`purge_request_logs`). Choose a retention period and body logging policy that fit your data handling requirements. `docker compose down` retains the database volume; `docker compose down -v` deletes it.

Point an OpenAI SDK at `http://localhost:8000/v1` and use `PROXY_API_KEY` as its API key. The proxy supports `GET /v1/models` and `POST /v1/chat/completions`, including streaming chat completions. If no models are configured, `/v1/models` is forwarded to the upstream provider. Set `UPSTREAM_MODEL_MAP` to a JSON object to map public model names to upstream names, for example `'{"my-model":"provider-model-v2"}'`.

You can manage routes at `/admin/` under **Model routes**. Create a route with the model name your client will request as **Public name** and the provider's model name as **Upstream name**. Optionally set **Upstream base URL** to route chat completions to a different provider address; leave it blank to use `UPSTREAM_BASE_URL`. Routes appear in `/v1/models` and chat requests using that public name are sent upstream with the mapped name and address. You can edit or delete routes in the same admin page. Database routes take precedence over `UPSTREAM_MODEL_MAP`; configured `UPSTREAM_MODELS` and environment map names remain available alongside database routes. Apply migrations after deploying with `python manage.py migrate`.

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

See [PLAN.md](PLAN.md) for the roadmap and remaining work. The initial implementation covers models and chat completions; other OpenAI endpoints and multi-provider routing remain future work.
