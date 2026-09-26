"""FastAPI Guest Token & Transit Analytics Service for KoridorTJ.

Mints short-lived guest tokens for anonymous embedded dashboard visitors,
serves live transit KPIs from the PostgreSQL warehouse, and hosts the public web portal.
"""

import os
import time
from datetime import UTC, datetime, timedelta

import jwt
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Load environment variables
load_dotenv()

app = FastAPI(
    title="KoridorTJ Transit Analytics & Guest Token API",
    description="Backend API for guest token minting, live transit telemetry, and embedded dashboard support.",
    version="1.0.0",
)

# Enable CORS for public frontend embedding
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", 5432))
POSTGRES_DB = os.getenv("POSTGRES_DB_WAREHOUSE", "warehouse")
POSTGRES_USER = os.getenv("POSTGRES_READONLY_USER", "superset_ro")
POSTGRES_PASSWORD = os.getenv("POSTGRES_READONLY_PASSWORD", "superset_ro_dev_password")

SUPERSET_DOMAIN = os.getenv("SUPERSET_DOMAIN", "http://localhost:8088")
SUPERSET_DASHBOARD_ID = os.getenv("SUPERSET_DASHBOARD_ID", "45d44fda-4e9c-4a88-894d-819f66fbfd33")
SUPERSET_JWT_SECRET = os.getenv(
    "SUPERSET_GUEST_TOKEN_JWT_SECRET", "koridortj_guest_token_jwt_secret_abcdef123456"
)

SUPERSET_JWT_ALGO = "HS256"
SUPERSET_JWT_EXP_SECONDS = 3600

START_TIME = time.time()


def get_db_connection():
    """Establish connection to PostgreSQL warehouse using read-only role."""
    return psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=5,
    )


class GuestTokenResponse(BaseModel):
    token: str
    dashboard_id: str
    superset_domain: str
    expires_in_seconds: int
    issued_at: str


@app.get("/health", tags=["Monitoring"])
def health_check():
    """Health check endpoint confirming service and database connectivity."""
    db_status = "unhealthy"
    try:
        conn = get_db_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
        conn.close()
        db_status = "healthy"
    except Exception as exc:
        db_status = f"error: {str(exc)}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "database": db_status,
        "timestamp": datetime.now(UTC).isoformat(),
        "disclaimer": "All passenger tap transactions are simulated data for demonstration purposes.",
    }


@app.get("/api/guest-token", response_model=GuestTokenResponse, tags=["Security"])
def mint_guest_token(dashboard_id: str | None = None):
    """Mints a short-lived signed JWT guest token for Superset embedded dashboard."""
    target_dashboard = dashboard_id or SUPERSET_DASHBOARD_ID
    now = datetime.now(UTC)
    exp = now + timedelta(seconds=SUPERSET_JWT_EXP_SECONDS)

    payload = {
        "user": {
            "username": "public_guest",
            "first_name": "Public",
            "last_name": "Guest",
        },
        "resources": [
            {
                "type": "dashboard",
                "id": target_dashboard,
            }
        ],
        "rls": [],
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }

    try:
        token = jwt.encode(payload, SUPERSET_JWT_SECRET, algorithm=SUPERSET_JWT_ALGO)
        return GuestTokenResponse(
            token=token,
            dashboard_id=target_dashboard,
            superset_domain=SUPERSET_DOMAIN,
            expires_in_seconds=SUPERSET_JWT_EXP_SECONDS,
            issued_at=now.isoformat(),
        )
    except Exception as err:
        raise HTTPException(status_code=500, detail=f"Failed to generate guest token: {err}")


@app.get("/api/stats", tags=["Analytics"])
def get_live_stats():
    """Fetch live aggregate transit metrics and analytical summaries from the warehouse."""
    try:
        conn = get_db_connection()
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Overall KPIs
            cur.execute("""
                SELECT
                    count(*) as total_taps,
                    count(distinct trans_id) as total_trips,
                    count(distinct pay_card_id) as unique_passengers,
                    count(distinct route_id) as active_routes,
                    count(distinct stop_id) as active_stops,
                    sum(case when is_simulated then 1 else 0 end) as simulated_taps,
                    min(tap_timestamp) as min_time,
                    max(tap_timestamp) as max_time
                FROM warehouse.fact_taps;
            """)
            kpis = dict(cur.fetchone())

            # Top 5 Busiest Boarding Stops
            cur.execute("""
                SELECT
                    s.stop_name,
                    s.latitude,
                    s.longitude,
                    count(*) as tap_count
                FROM warehouse.fact_taps f
                JOIN warehouse.dim_stops s ON f.stop_id = s.stop_id
                WHERE f.tap_type = 'IN'
                GROUP BY s.stop_name, s.latitude, s.longitude
                ORDER BY tap_count DESC
                LIMIT 5;
            """)
            top_stops = [dict(r) for r in cur.fetchall()]

            # Ridership by Card Bank
            cur.execute("""
                SELECT
                    coalesce(pay_card_bank, 'unknown') as bank,
                    count(*) as tap_count
                FROM warehouse.fact_taps
                GROUP BY bank
                ORDER BY tap_count DESC;
            """)
            by_bank = [dict(r) for r in cur.fetchall()]

            # Hourly distribution
            cur.execute("""
                SELECT
                    extract(hour from tap_timestamp)::int as hour_of_day,
                    count(*) as tap_count
                FROM warehouse.fact_taps
                WHERE tap_type = 'IN'
                GROUP BY hour_of_day
                ORDER BY hour_of_day;
            """)
            hourly = [dict(r) for r in cur.fetchall()]

        conn.close()

        return {
            "status": "success",
            "kpis": kpis,
            "top_boarding_stops": top_stops,
            "bank_market_share": by_bank,
            "hourly_distribution": hourly,
            "data_disclaimer": "Simulated passenger tap-in/tap-out transaction data modeled for portfolio demonstration.",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database query failed: {exc}")


# Mount web directory (supports local dev repo structure, current working dir, and Docker /app/web)
possible_paths = [
    os.path.join(os.path.dirname(__file__), "web"),
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "web"),
    os.path.join(os.getcwd(), "web"),
    "/app/web",
]
web_dir = next((p for p in possible_paths if os.path.exists(p) and os.path.isdir(p)), None)
if web_dir:
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
