"""Unit tests for the Guest Token and Transit Telemetry FastAPI service."""

import jwt
from fastapi.testclient import TestClient

from services.guest_token_service.main import (
    SUPERSET_JWT_ALGO,
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
        )

        assert decoded["user"]["username"] == "public_guest"
        assert len(decoded["resources"]) == 1
        assert decoded["resources"][0]["type"] == "dashboard"
        assert decoded["resources"][0]["id"] == "test-dashboard-123"
        assert decoded["exp"] > decoded["iat"]
