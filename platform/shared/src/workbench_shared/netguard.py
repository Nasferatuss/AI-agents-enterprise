"""SSRF guard for agent-driven outbound HTTP.

Agent tools (``fetch_url``, deep-research ``fetch``, live-browse ``navigate``)
take a URL chosen by the LLM. Without a guard, a prompt-injected agent can be
steered at internal addresses — most dangerously the cloud metadata endpoint
(``169.254.169.254``) to exfiltrate IAM credentials, or ``127.0.0.1``/RFC-1918
hosts behind the deploy.

``assert_public_url`` is the single chokepoint: it rejects non-http(s) schemes
and resolves the host, requiring **every** resolved address to be globally
routable. ``safe_get`` additionally re-validates each redirect hop, since a
public URL can 30x to an internal one.

Stdlib-only at import time; ``httpx`` is imported lazily inside ``safe_get`` so
this module stays a cheap dependency for non-fetching callers.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = ("http", "https")
_MAX_REDIRECTS = 5


class UnsafeUrlError(ValueError):
    """Raised when a URL is not safe to fetch (bad scheme or private target)."""


def _ip_is_public(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    # Block loopback, RFC-1918/ULA private, link-local (incl. 169.254.169.254
    # cloud metadata), multicast, reserved, unspecified.
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def assert_public_url(url: str, *, allowed_schemes: tuple[str, ...] = _ALLOWED_SCHEMES) -> str:
    """Return ``url`` if it is safe to fetch, else raise ``UnsafeUrlError``.

    Safe = an allowed scheme, a hostname present, and every DNS-resolved address
    globally routable. DNS is resolved here (not just the literal host) so that a
    name pointing at ``127.0.0.1`` or a metadata IP is caught too.
    """
    if not url or not url.strip():
        raise UnsafeUrlError("empty url")
    parts = urlsplit(url.strip())
    if parts.scheme.lower() not in allowed_schemes:
        raise UnsafeUrlError(f"scheme not allowed: {parts.scheme or '(none)'}")
    host = parts.hostname
    if not host:
        raise UnsafeUrlError("url has no host")

    # If the host is already an IP literal, classify it directly.
    try:
        ipaddress.ip_address(host)
        literal_ip = True
    except ValueError:
        literal_ip = False
    if literal_ip:
        if not _ip_is_public(host):
            raise UnsafeUrlError(f"host resolves to a non-public address: {host}")
        return url

    try:
        infos = socket.getaddrinfo(host, parts.port or None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"cannot resolve host {host}: {exc}") from exc
    addrs = {info[4][0] for info in infos}
    if not addrs:
        raise UnsafeUrlError(f"host {host} resolved to no addresses")
    for ip in addrs:
        if not _ip_is_public(ip):
            raise UnsafeUrlError(f"host {host} resolves to a non-public address: {ip}")
    return url


def safe_get(url: str, *, max_redirects: int = _MAX_REDIRECTS, **kwargs):
    """``httpx.get`` with SSRF validation on the initial URL and every redirect hop.

    Redirects are followed manually so each ``Location`` is re-validated — a public
    URL that 30x-es to ``169.254.169.254`` is blocked mid-chain. ``kwargs`` pass
    through to ``httpx`` (``timeout``, ``headers``, …). Raises ``UnsafeUrlError`` on
    an unsafe hop; the final non-redirect response is returned with redirects off.
    """
    import httpx

    kwargs.pop("follow_redirects", None)
    current = assert_public_url(url)
    with httpx.Client(follow_redirects=False, **kwargs) as client:
        for _ in range(max_redirects + 1):
            resp = client.get(current)
            if not resp.is_redirect or "location" not in resp.headers:
                return resp
            current = assert_public_url(str(resp.url.join(resp.headers["location"])))
    raise UnsafeUrlError(f"too many redirects (>{max_redirects})")
