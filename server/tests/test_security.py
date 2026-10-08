from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware


def test_security_headers_and_rate_limit() -> None:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware, requests_per_minute=2, chat_requests_per_minute=1)

    @app.get("/api/test")
    def endpoint() -> dict:
        return {"ok": True}

    client = TestClient(app)
    first = client.get("/api/test")
    second = client.get("/api/test")
    third = client.get("/api/test")

    assert first.headers["X-Content-Type-Options"] == "nosniff"
    assert first.headers["X-Frame-Options"] == "DENY"
    assert "X-Request-ID" in first.headers
    assert second.status_code == 200
    assert third.status_code == 429
    assert "Retry-After" in third.headers
