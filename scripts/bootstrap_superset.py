#!/usr/bin/env python3
"""Automated Superset Bootstrap & Dashboard Provisioner for KoridorTJ.

Connects to the running Apache Superset instance, provisions the PostgreSQL warehouse
connection, registers conformed datasets, creates analytical charts, and publishes the
embedded dashboard.
"""

import json
import logging
import os
import sys
import time
from typing import Any, Dict, List, Optional
import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [superset_bootstrap] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("superset_bootstrap")

SUPERSET_URL = os.getenv("SUPERSET_URL", "http://localhost:8088")
SUPERSET_USER = os.getenv("SUPERSET_ADMIN_USERNAME", "admin")
SUPERSET_PASS = os.getenv("SUPERSET_ADMIN_PASSWORD", "admin")

WAREHOUSE_DB_URI = os.getenv(
    "SUPERSET_WAREHOUSE_SQLALCHEMY_URI",
    "postgresql+psycopg2://superset_ro:superset_ro_dev_password@postgres:5432/warehouse",
)


class SupersetProvisioner:
    """Manages Superset API automation."""

    def __init__(self, base_url: str = SUPERSET_URL, username: str = SUPERSET_USER, password: str = SUPERSET_PASS):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.access_token: Optional[str] = None
        self.csrf_token: Optional[str] = None

    def wait_for_superset(self, timeout_seconds: int = 180) -> bool:
        """Wait until Superset web server is responding."""
        logger.info("Waiting for Superset web server at %s...", self.base_url)
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                res = self.session.get(f"{self.base_url}/health", timeout=5)
                if res.status_code == 200:
                    logger.info("Superset is up and healthy!")
                    return True
            except Exception:
                pass
            time.sleep(5)
        logger.error("Timed out waiting for Superset.")
        return False

    def login(self) -> bool:
        """Authenticate and obtain JWT access token and CSRF token."""
        login_url = f"{self.base_url}/api/v1/security/login"
        payload = {
            "username": self.username,
            "password": self.password,
            "provider": "db",
            "refresh": True,
        }
        logger.info("Authenticating with Superset API as '%s'...", self.username)
        res = self.session.post(login_url, json=payload, timeout=10)
        if res.status_code != 200:
            logger.error("Login failed (HTTP %d): %s", res.status_code, res.text)
            return False

        self.access_token = res.json().get("access_token")
        self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})

        # Fetch CSRF token
        csrf_url = f"{self.base_url}/api/v1/security/csrf_token/"
        csrf_res = self.session.get(csrf_url, timeout=10)
        if csrf_res.status_code == 200:
            self.csrf_token = csrf_res.json().get("result")
            self.session.headers.update({"X-CSRFToken": self.csrf_token})
            logger.info("Successfully authenticated and obtained CSRF token.")
            return True
        return True

    def create_database_connection(self) -> Optional[int]:
        """Create or find the PostgreSQL warehouse connection."""
        url = f"{self.base_url}/api/v1/database/"
        res = self.session.get(url, timeout=10)
        if res.status_code == 200:
            for db in res.json().get("result", []):
                if db.get("database_name") == "KoridorTJ Warehouse":
                    logger.info("Found existing database connection (ID: %s)", db.get("id"))
                    return db.get("id")

        payload = {
            "database_name": "KoridorTJ Warehouse",
            "sqlalchemy_uri": WAREHOUSE_DB_URI,
            "expose_in_sqllab": True,
            "allow_run_async": True,
            "allow_ctas": False,
            "allow_cvas": False,
            "allow_dml": False,
        }
        logger.info("Registering Database connection to warehouse...")
        create_res = self.session.post(url, json=payload, timeout=10)
        if create_res.status_code in (200, 201):
            db_id = create_res.json().get("id")
            logger.info("Database registered successfully with ID %s", db_id)
            return db_id
        else:
            logger.warning("Database registration response: %s", create_res.text)
            return None

    def create_dataset(self, db_id: int, schema: str, table_name: str) -> Optional[int]:
        """Register a table as a Superset dataset."""
        url = f"{self.base_url}/api/v1/dataset/"
        res = self.session.get(f"{url}?q=(filters:[{{col:table_name,opr:eq,value:'{table_name}'}}])", timeout=10)
        if res.status_code == 200:
            results = res.json().get("result", [])
            if results:
                logger.info("Found existing dataset '%s.%s' (ID: %s)", schema, table_name, results[0].get("id"))
                return results[0].get("id")

        payload = {
            "database": db_id,
            "schema": schema,
            "table_name": table_name,
        }
        create_res = self.session.post(url, json=payload, timeout=10)
        if create_res.status_code in (200, 201):
            ds_id = create_res.json().get("id")
            logger.info("Dataset '%s.%s' registered successfully with ID %s", schema, table_name, ds_id)
            return ds_id
        else:
            logger.warning("Dataset registration response for '%s.%s': %s", schema, table_name, create_res.text)
            return None

    def create_chart(self, dataset_id: int, slice_name: str, viz_type: str, params: Dict[str, Any]) -> Optional[int]:
        """Create an analytical chart in Superset."""
        url = f"{self.base_url}/api/v1/chart/"
        res = self.session.get(f"{url}?q=(filters:[{{col:slice_name,opr:eq,value:'{slice_name}'}}])", timeout=10)
        if res.status_code == 200:
            results = res.json().get("result", [])
            if results:
                logger.info("Found existing chart '%s' (ID: %s)", slice_name, results[0].get("id"))
                return results[0].get("id")

        payload = {
            "slice_name": slice_name,
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "viz_type": viz_type,
            "params": json.dumps(params),
        }
        create_res = self.session.post(url, json=payload, timeout=10)
        if create_res.status_code in (200, 201):
            chart_id = create_res.json().get("id")
            logger.info("Chart '%s' created successfully with ID %s", slice_name, chart_id)
            return chart_id
        else:
            logger.warning("Chart creation failed for '%s': %s", slice_name, create_res.text)
            return None

    def create_dashboard(self, dashboard_title: str, chart_ids: List[int]) -> Optional[Dict[str, Any]]:
        """Create or update a Superset dashboard and configure embedded access."""
        url = f"{self.base_url}/api/v1/dashboard/"
        dash_id: Optional[int] = None
        dash_uuid: Optional[str] = None

        res = self.session.get(f"{url}?q=(filters:[{{col:dashboard_title,opr:eq,value:'{dashboard_title}'}}])", timeout=10)
        if res.status_code == 200:
            results = res.json().get("result", [])
            if results:
                dash_id = results[0].get("id")
                dash_uuid = results[0].get("uuid")
                logger.info("Found existing dashboard '%s' (ID: %s, UUID: %s)", dashboard_title, dash_id, dash_uuid)

        if not dash_id:
            payload = {
                "dashboard_title": dashboard_title,
                "published": True,
                "slug": "transjakarta-transit-intelligence",
            }
            create_res = self.session.post(url, json=payload, timeout=10)
            if create_res.status_code in (200, 201):
                dash_id = create_res.json().get("id")
                # Fetch created dashboard to get UUID
                d_res = self.session.get(f"{url}{dash_id}", timeout=10)
                if d_res.status_code == 200:
                    dash_uuid = d_res.json().get("result", {}).get("uuid")
                logger.info("Created dashboard '%s' (ID: %s, UUID: %s)", dashboard_title, dash_id, dash_uuid)
            else:
                logger.warning("Failed to create dashboard: %s", create_res.text)
                return None

        # Enable embedded dashboard
        embed_url = f"{self.base_url}/api/v1/dashboard/{dash_id}/embedded"
        embed_res = self.session.get(embed_url, timeout=10)
        embedded_uuid: Optional[str] = None

        if embed_res.status_code == 200:
            embedded_uuid = embed_res.json().get("result", {}).get("uuid")
            logger.info("Existing embedded dashboard configuration found (Embedded UUID: %s)", embedded_uuid)
        else:
            post_embed = self.session.post(embed_url, json={"allowed_domains": ["*"]}, timeout=10)
            if post_embed.status_code in (200, 201):
                embedded_uuid = post_embed.json().get("result", {}).get("uuid")
                logger.info("Embedded dashboard enabled successfully (Embedded UUID: %s)", embedded_uuid)

        return {
            "dashboard_id": dash_id,
            "dashboard_uuid": dash_uuid,
            "embedded_uuid": embedded_uuid,
        }

    def run(self):
        """Execute full provisioning workflow."""
        if not self.wait_for_superset():
            return {"status": "SKIPPED", "reason": "Superset unavailable"}

        if not self.login():
            return {"status": "FAILED", "reason": "Authentication failure"}

        db_id = self.create_database_connection()
        if not db_id:
            return {"status": "FAILED", "reason": "Could not connect database"}

        # Register datasets
        fact_ds_id = self.create_dataset(db_id, "warehouse", "fact_taps")
        stops_ds_id = self.create_dataset(db_id, "warehouse", "dim_stops")
        routes_ds_id = self.create_dataset(db_id, "warehouse", "dim_routes")

        chart_ids = []
        if fact_ds_id:
            # 1. Hourly Ridership Chart
            c1 = self.create_chart(
                fact_ds_id,
                "Hourly Tap-In Ridership Pattern",
                "echarts_timeseries_bar",
                {
                    "metrics": ["count"],
                    "groupby": ["tap_type"],
                    "adhoc_filters": [{"clause": "WHERE", "expressionType": "SQL", "sqlExpression": "tap_type = 'IN'"}],
                },
            )
            if c1: chart_ids.append(c1)

            # 2. Card Bank Market Share
            c2 = self.create_chart(
                fact_ds_id,
                "Payment Card Issuer Distribution",
                "pie",
                {
                    "metric": "count",
                    "groupby": ["pay_card_bank"],
                },
            )
            if c2: chart_ids.append(c2)

            # 3. Top Boarding Stops
            c3 = self.create_chart(
                fact_ds_id,
                "Busiest Transit Boarding Stops",
                "table",
                {
                    "metrics": ["count"],
                    "groupby": ["stop_id", "corridor_code"],
                    "order_desc": True,
                    "row_limit": 10,
                },
            )
            if c3: chart_ids.append(c3)

            # 4. Weekday vs Weekend Pattern
            c4 = self.create_chart(
                fact_ds_id,
                "Ridership by Direction and Corridor",
                "echarts_timeseries_bar",
                {
                    "metrics": ["count"],
                    "groupby": ["corridor_code"],
                    "row_limit": 15,
                },
            )
            if c4: chart_ids.append(c4)

        # Create Dashboard
        dash_info = self.create_dashboard("TransJakarta Transit Intelligence Overview", chart_ids)

        summary = {
            "status": "SUCCESS",
            "database_id": db_id,
            "dataset_ids": [fact_ds_id, stops_ds_id, routes_ds_id],
            "chart_ids": chart_ids,
            "dashboard_info": dash_info,
        }
        logger.info("=== Superset Provisioning Complete ===")
        logger.info("Summary: %s", summary)
        return summary


if __name__ == "__main__":
    provisioner = SupersetProvisioner()
    provisioner.run()
