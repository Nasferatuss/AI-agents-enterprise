"""Network-free unit tests for the SSRF guard (``workbench_shared.netguard``).

All cases use IP literals so ``assert_public_url`` never touches DNS or the
network — the only socket-touching path (``socket.getaddrinfo``) is skipped for
literal hosts, and ``safe_get`` is exercised against a mocked ``httpx.Client``.
"""

from __future__ import annotations

from unittest import mock

import pytest

from workbench_shared.netguard import UnsafeUrlError, assert_public_url, safe_get

BLOCKED_URLS = [
    "http://127.0.0.1/",  # loopback
    "http://10.0.0.5/",  # RFC1918
    "http://172.16.0.1/",  # RFC1918
    "http://192.168.1.1/",  # RFC1918
    "http://169.254.169.254/",  # link-local cloud metadata
    "http://100.64.0.1/",  # RFC 6598 CGNAT
    "http://224.0.0.1/",  # multicast
    "http://[::1]/",  # IPv6 loopback
    "http://[fc00::1]/",  # IPv6 ULA
    "http://[::ffff:169.254.169.254]/",  # IPv6-mapped metadata
    "http://2852039166/",  # decimal-notation 169.254.169.254
    "http://0xa9fea9fe/",  # hex-notation 169.254.169.254
    "http://0251.0376.0251.0376/",  # octal-notation 169.254.169.254
]

BAD_SCHEME_URLS = [
    "file:///etc/passwd",
    "gopher://x",
    "",
]


@pytest.mark.parametrize("url", BLOCKED_URLS)
def test_blocks_non_public_targets(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        assert_public_url(url)


@pytest.mark.parametrize("url", BAD_SCHEME_URLS)
def test_rejects_non_http_schemes(url: str) -> None:
    with pytest.raises(UnsafeUrlError):
        assert_public_url(url)


def test_allows_public_literal() -> None:
    url = "http://93.184.216.34/"
    assert assert_public_url(url) == url


def test_safe_get_rejects_unsafe_url_before_network() -> None:
    # An initially-unsafe URL must raise before any httpx.Client is constructed.
    with mock.patch("httpx.Client") as client_cls:
        with pytest.raises(UnsafeUrlError):  # noqa: SIM117 — assert after the block
            safe_get("http://169.254.169.254/")
        client_cls.assert_not_called()


def test_safe_get_revalidates_redirect_hop() -> None:
    # First hop is a public 302 -> metadata IP; the redirect must be blocked.
    redirect_resp = mock.Mock()
    redirect_resp.is_redirect = True
    redirect_resp.headers = {"location": "http://169.254.169.254/"}
    # resp.url.join(location) -> the absolute redirect target.
    redirect_resp.url.join.return_value = "http://169.254.169.254/"

    client = mock.MagicMock()
    client.get.return_value = redirect_resp
    client.__enter__.return_value = client
    client.__exit__.return_value = False

    with mock.patch("httpx.Client", return_value=client), pytest.raises(UnsafeUrlError):
        safe_get("http://93.184.216.34/")
