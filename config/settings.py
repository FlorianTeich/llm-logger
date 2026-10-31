"""Django settings for the LLM proxy."""

import os
import json
from pathlib import Path
from urllib.parse import unquote, urlparse

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
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
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
    "whitenoise.middleware.WhiteNoiseMiddleware",
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

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    parsed_database_url = urlparse(DATABASE_URL)
    if parsed_database_url.scheme in {"postgres", "postgresql", "postgresql+psycopg"}:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": unquote(parsed_database_url.path.lstrip("/")),
                "USER": unquote(parsed_database_url.username or ""),
                "PASSWORD": unquote(parsed_database_url.password or ""),
                "HOST": parsed_database_url.hostname or "",
                "PORT": parsed_database_url.port or "",
                "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
                "OPTIONS": {"sslmode": os.environ.get("DB_SSLMODE", "prefer")},
            }
        }
    elif parsed_database_url.scheme == "sqlite":
        sqlite_path = unquote(parsed_database_url.path)
        if parsed_database_url.netloc:
            sqlite_path = f"//{parsed_database_url.netloc}{sqlite_path}"
        DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": sqlite_path}}
    else:
        raise ImproperlyConfigured("DATABASE_URL must use postgres://, postgresql://, or sqlite://.")
else:
    if os.environ.get("DB_HOST"):
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": os.environ.get("DB_NAME", "llm_proxy"),
                "USER": os.environ.get("DB_USER", "llm_proxy"),
                "PASSWORD": os.environ.get("DB_PASSWORD", ""),
                "HOST": os.environ["DB_HOST"],
                "PORT": os.environ.get("DB_PORT", "5432"),
                "CONN_MAX_AGE": int(os.environ.get("DB_CONN_MAX_AGE", "60")),
                "OPTIONS": {"sslmode": os.environ.get("DB_SSLMODE", "prefer")},
            }
        }
    else:
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
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SECURE_SSL_REDIRECT", "false").lower() == "true"
if os.environ.get("DJANGO_SECURE_PROXY_SSL_HEADER", "false").lower() == "true":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
if os.environ.get("DJANGO_SECURE_HSTS_SECONDS"):
    SECURE_HSTS_SECONDS = int(os.environ["DJANGO_SECURE_HSTS_SECONDS"])
    SECURE_HSTS_INCLUDE_SUBDOMAINS = os.environ.get("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", "false").lower() == "true"
    SECURE_HSTS_PRELOAD = os.environ.get("DJANGO_SECURE_HSTS_PRELOAD", "false").lower() == "true"
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
