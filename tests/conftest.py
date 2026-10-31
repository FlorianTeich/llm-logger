import pytest


@pytest.fixture(autouse=True)
def proxy_settings(settings):
    settings.DEBUG = False
    settings.ALLOWED_HOSTS = ["testserver", "localhost"]
    settings.PROXY_API_KEY = "test-proxy-key"
    settings.UPSTREAM_BASE_URL = "https://upstream.test/v1"
    settings.UPSTREAM_API_KEY = "test-upstream-key"
    settings.UPSTREAM_TIMEOUT_SECONDS = 2
    settings.UPSTREAM_MODELS = []
    settings.UPSTREAM_MODEL_MAP = {}
    settings.REQUEST_LOG_STORE_BODIES = True
    settings.REQUEST_LOG_MAX_BODY_BYTES = 0
    settings.REQUEST_LOG_REDACT_FIELDS = {
        "api_key",
        "authorization",
        "password",
        "secret",
        "access_token",
        "refresh_token",
    }


@pytest.fixture
def auth_headers():
    return {"HTTP_AUTHORIZATION": "Bearer test-proxy-key"}
