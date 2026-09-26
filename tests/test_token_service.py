"""Unit tests for the Guest Token and Transit Telemetry FastAPI service."""

import jwt
from fastapi.testclient import TestClient

from services.guest_token_service.main import (
    SUPERSET_JWT_ALGO,
    SUPERSET_JWT_AUDIENCE,
    SUPERSET_JWT_SECRET,
    app,
)

client = TestClient(app)


class TestGuestTokenService:
    """Test suite for FastAPI endpoints."""

    def test_health_check_endpoint(self):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "disclaimer" in data
        assert "simulated" in data["disclaimer"].lower()

    def test_mint_guest_token_jwt_signature_and_claims(self):
        response = client.get("/api/guest-token?dashboard_id=test-dashboard-123")
        assert response.status_code == 200
        data = response.json()

        assert "token" in data
        assert data["dashboard_id"] == "test-dashboard-123"
        assert data["expires_in_seconds"] == 3600

        # Decode and verify JWT signature
        decoded = jwt.decode(
            data["token"],
            SUPERSET_JWT_SECRET,
            algorithms=[SUPERSET_JWT_ALGO],
            audience=SUPERSET_JWT_AUDIENCE,
        )

        assert decoded["user"]["username"] == "public_guest"
        assert decoded["aud"] == SUPERSET_JWT_AUDIENCE
        assert decoded["type"] == "guest"
        assert decoded["rls_rules"] == []
        assert len(decoded["resources"]) == 1
        assert decoded["resources"][0]["type"] == "dashboard"
        assert decoded["resources"][0]["id"] == "test-dashboard-123"
        assert decoded["exp"] > decoded["iat"]

    def test_web_portal_root_endpoint(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")
        assert "KoridorTJ" in response.text

    def test_favicon_endpoints(self):
        response_ico = client.get("/favicon.ico")
        assert response_ico.status_code in (200, 204)
        if response_ico.status_code == 200:
            assert "image" in response_ico.headers.get("content-type", "")

        response_svg = client.get("/favicon.svg")
        assert response_svg.status_code in (200, 204)
        if response_svg.status_code == 200:
            assert "image/svg+xml" in response_svg.headers.get("content-type", "")
