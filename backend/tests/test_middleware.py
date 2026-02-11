import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_request_id_in_response():
    """All responses include X-Request-ID header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert "X-Request-ID" in response.headers
    # UUID format: 8-4-4-4-12
    request_id = response.headers["X-Request-ID"]
    assert len(request_id) == 36


@pytest.mark.asyncio
async def test_404_returns_structured_json():
    """Non-existent endpoint returns structured JSON error with request_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/nonexistent")
    assert response.status_code == 404
    data = response.json()
    assert data["error"] is True
    assert data["status_code"] == 404
    assert "request_id" in data
