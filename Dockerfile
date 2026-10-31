FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --no-dev --frozen --no-install-project

COPY . .
RUN uv run --no-sync python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "125", "--access-logfile", "-", "--error-logfile", "-"]
