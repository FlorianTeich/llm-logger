"""Django settings for the LLM proxy."""

import os
import json
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-only-change-me")
if not DEBUG and SECRET_KEY == "dev-only-change-me":
    raise ImproperlyConfigured("Set DJANGO_SECRET_KEY when DJANGO_DEBUG is false.")
ALLOWED_HOSTS = [
    host.strip()
    for host in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if host.strip()
]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "proxy",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("DATABASE_PATH", str(BASE_DIR / "db.sqlite3")),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.environ.get("TZ", "UTC")
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_REDIRECT_URL = "/logs/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# Provider and proxy credentials are intentionally sourced from the environment.
UPSTREAM_BASE_URL = os.environ.get("UPSTREAM_BASE_URL", "https://api.openai.com/v1")
UPSTREAM_API_KEY = os.environ.get("UPSTREAM_API_KEY", "")
UPSTREAM_TIMEOUT_SECONDS = float(os.environ.get("UPSTREAM_TIMEOUT_SECONDS", "120"))
UPSTREAM_MODELS = [
    model.strip()
    for model in os.environ.get("UPSTREAM_MODELS", "").split(",")
    if model.strip()
]
try:
    UPSTREAM_MODEL_MAP = json.loads(os.environ.get("UPSTREAM_MODEL_MAP", "{}"))
except json.JSONDecodeError as exc:
    raise ValueError("UPSTREAM_MODEL_MAP must be valid JSON") from exc
if not isinstance(UPSTREAM_MODEL_MAP, dict) or not all(
    isinstance(key, str) and isinstance(value, str)
    for key, value in UPSTREAM_MODEL_MAP.items()
):
    raise ValueError("UPSTREAM_MODEL_MAP must be a JSON object of string model names")
if UPSTREAM_TIMEOUT_SECONDS <= 0:
    raise ValueError("UPSTREAM_TIMEOUT_SECONDS must be greater than zero")
if not UPSTREAM_BASE_URL.startswith(("http://", "https://")):
    raise ValueError("UPSTREAM_BASE_URL must be an absolute HTTP or HTTPS URL")
PROXY_API_KEY = os.environ.get("PROXY_API_KEY", "")
REQUEST_LOG_MAX_BODY_BYTES = int(os.environ.get("REQUEST_LOG_MAX_BODY_BYTES", "0"))
if REQUEST_LOG_MAX_BODY_BYTES < 0:
    raise ValueError("REQUEST_LOG_MAX_BODY_BYTES cannot be negative")
REQUEST_LOG_RETENTION_DAYS = int(os.environ.get("REQUEST_LOG_RETENTION_DAYS", "90"))
REQUEST_LOG_STORE_BODIES = os.environ.get("REQUEST_LOG_STORE_BODIES", "true").lower() == "true"
REQUEST_LOG_REDACT_FIELDS = {
    field.strip().lower()
    for field in os.environ.get(
        "REQUEST_LOG_REDACT_FIELDS",
        "api_key,authorization,password,secret,access_token,refresh_token",
    ).split(",")
    if field.strip()
}
