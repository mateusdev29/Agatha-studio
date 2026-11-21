from urllib.parse import urljoin, urlparse

from flask import request


def is_safe_redirect_url(target: str | None) -> bool:
    """Aceita apenas URLs do mesmo host (evita open redirect via ?next=)."""
    if not target:
        return False
    ref = urlparse(request.host_url)
    test = urlparse(urljoin(request.host_url, target))
    return test.scheme in ("http", "https") and ref.netloc == test.netloc
