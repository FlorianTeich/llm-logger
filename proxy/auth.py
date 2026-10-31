import hmac

from django.conf import settings


def proxy_key_is_valid(request) -> bool:
    expected = settings.PROXY_API_KEY
    if not expected:
        # A missing key is only an intentional open mode in local development.
        return settings.DEBUG

    authorization = request.headers.get("Authorization", "")
    parts = authorization.strip().split(None, 1)
    return (
        len(parts) == 2
        and parts[0].lower() == "bearer"
        and hmac.compare_digest(parts[1], expected)
    )
