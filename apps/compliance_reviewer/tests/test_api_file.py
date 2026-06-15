import httpx
from fastapi import FastAPI

from workbench_app_compliance import api
from workbench_runtime.router import ModelRouter


def _no_provider_router() -> ModelRouter:
    """No provider → review returns deterministic findings, no network."""
    router = ModelRouter(registry={})
    router.chain = lambda complexity: []  # type: ignore[method-assign]
    return router


def _app(monkeypatch) -> FastAPI:
    monkeypatch.setattr(api, "get_router", _no_provider_router)
    app = FastAPI()
    app.include_router(api.router)
    return app


async def _client(monkeypatch) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=_app(monkeypatch))
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_txt_upload_returns_report_with_pii_findings(monkeypatch):
    # 4111-1111-1111-1111 is a Luhn-valid test card → credit_card finding.
    text = b"Customer card on file: 4111 1111 1111 1111. Contact a@b.com."
    async with await _client(monkeypatch) as c:
        resp = await c.post(
            "/v1/apps/compliance/review/file",
            files={"file": ("doc.txt", text, "text/plain")},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert any(f["type"] == "credit_card" for f in body["pii_findings"])
    assert body["risk_score"] > 0


async def test_unsupported_extension_415(monkeypatch):
    async with await _client(monkeypatch) as c:
        resp = await c.post(
            "/v1/apps/compliance/review/file",
            files={"file": ("doc.xyz", b"whatever", "application/octet-stream")},
        )
    assert resp.status_code == 415


async def test_empty_text_422(monkeypatch):
    async with await _client(monkeypatch) as c:
        resp = await c.post(
            "/v1/apps/compliance/review/file",
            files={"file": ("doc.txt", b"   \n  ", "text/plain")},
        )
    assert resp.status_code == 422
