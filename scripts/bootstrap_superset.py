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
import urllib.parse
from typing import Any

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

RO_USER = os.getenv("POSTGRES_READONLY_USER", "superset_ro")
RO_PASS = os.getenv("POSTGRES_READONLY_PASSWORD", "superset_ro_dev_password")
PG_HOST = os.getenv("POSTGRES_HOST", "postgres")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB = os.getenv("POSTGRES_DB_WAREHOUSE", "warehouse")

_encoded_ro_user = urllib.parse.quote_plus(RO_USER)
_encoded_ro_pass = urllib.parse.quote_plus(RO_PASS)
WAREHOUSE_DB_URI = os.getenv(
    "SUPERSET_WAREHOUSE_SQLALCHEMY_URI",
    f"postgresql+psycopg2://{_encoded_ro_user}:{_encoded_ro_pass}@{PG_HOST}:{PG_PORT}/{PG_DB}",
)

REQUEST_TIMEOUT = 60


class SupersetProvisioner:
    """Manages Superset API automation."""

    def __init__(
        self,
        base_url: str = SUPERSET_URL,
        username: str = SUPERSET_USER,
        password: str = SUPERSET_PASS,
    ):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.access_token: str | None = None
        self.csrf_token: str | None = None
        self.user_id: int = 1

    def wait_for_superset(self, timeout_seconds: int = 180) -> bool:
        """Wait until Superset web server is responding."""
        logger.info("Waiting for Superset web server at %s...", self.base_url)
        start = time.time()
        while time.time() - start < timeout_seconds:
            try:
                res = self.session.get(f"{self.base_url}/health", timeout=10)
                if res.status_code == 200:
                    logger.info("Superset is up and healthy!")
                    return True
            except Exception:
                pass
            time.sleep(5)
        logger.error("Timed out waiting for Superset.")
        return False

    def login(self, max_retries: int = 3) -> bool:
        """Authenticate and obtain JWT access token, CSRF token, and user ID."""
        login_url = f"{self.base_url}/api/v1/security/login"
        payload = {
            "username": self.username,
            "password": self.password,
            "provider": "db",
            "refresh": True,
        }

        for attempt in range(1, max_retries + 1):
            logger.info(
                "Authenticating with Superset API as '%s' (Attempt %d/%d)...",
                self.username,
                attempt,
                max_retries,
            )
            try:
                res = self.session.post(login_url, json=payload, timeout=REQUEST_TIMEOUT)
                if res.status_code != 200:
                    logger.error("Login failed (HTTP %d): %s", res.status_code, res.text)
                    if res.status_code == 401:
                        logger.error(
                            "Invalid credentials for user '%s'. Please verify SUPERSET_ADMIN_PASSWORD.",
                            self.username,
                        )
                        return False
                    time.sleep(3)
                    continue

                self.access_token = res.json().get("access_token")
                self.session.headers.update({"Authorization": f"Bearer {self.access_token}"})

                # Fetch CSRF token
                csrf_url = f"{self.base_url}/api/v1/security/csrf_token/"
                csrf_res = self.session.get(csrf_url, timeout=REQUEST_TIMEOUT)
                if csrf_res.status_code == 200:
                    self.csrf_token = csrf_res.json().get("result")
                    self.session.headers.update({"X-CSRFToken": self.csrf_token})

                # Fetch current user ID
                me_url = f"{self.base_url}/api/v1/me/"
                me_res = self.session.get(me_url, timeout=REQUEST_TIMEOUT)
                if me_res.status_code == 200:
                    self.user_id = me_res.json().get("result", {}).get("id", 1)

                logger.info(
                    "Successfully authenticated (User ID: %d) and obtained CSRF token.",
                    self.user_id,
                )
                return True
            except requests.exceptions.RequestException as e:
                logger.warning("Login attempt %d failed with error: %s", attempt, e)
                time.sleep(3)

        logger.error("Failed to authenticate with Superset after %d attempts.", max_retries)
        return False

    def create_database_connection(self) -> int | None:
        """Create or find the PostgreSQL warehouse connection."""
        url = f"{self.base_url}/api/v1/database/"
        try:
            res = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if res.status_code == 200:
                for db in res.json().get("result", []):
                    if db.get("database_name") == "KoridorTJ Warehouse":
                        db_id = db.get("id")
                        logger.info("Found existing database connection (ID: %s)", db_id)
                        self.session.put(
                            f"{url}{db_id}",
                            json={"expose_in_sqllab": True, "allow_run_async": False},
                            timeout=REQUEST_TIMEOUT,
                        )
                        return db_id
        except Exception as e:
            logger.warning("Error fetching databases: %s", e)

        payload = {
            "database_name": "KoridorTJ Warehouse",
            "sqlalchemy_uri": WAREHOUSE_DB_URI,
            "expose_in_sqllab": True,
            "allow_run_async": False,
            "allow_ctas": False,
            "allow_cvas": False,
            "allow_dml": False,
        }
        logger.info("Registering Database connection to warehouse...")
        create_res = self.session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        if create_res.status_code in (200, 201):
            db_id = create_res.json().get("id")
            logger.info("Database registered successfully with ID %s", db_id)
            return db_id
        else:
            logger.warning("Database registration response: %s", create_res.text)
            return None

    def create_dataset(self, db_id: int, schema: str, table_name: str) -> int | None:
        """Register a table as a Superset dataset."""
        url = f"{self.base_url}/api/v1/dataset/"
        try:
            res = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if res.status_code == 200:
                for ds in res.json().get("result", []):
                    if ds.get("table_name") == table_name and ds.get("schema") == schema:
                        ds_id = ds.get("id")
                        logger.info(
                            "Found existing dataset '%s.%s' (ID: %s)", schema, table_name, ds_id
                        )
                        return ds_id
        except Exception as e:
            logger.warning("Error fetching datasets: %s", e)

        payload = {
            "database": db_id,
            "schema": schema,
            "table_name": table_name,
            "owners": [self.user_id],
        }
        create_res = self.session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        if create_res.status_code in (200, 201):
            ds_id = create_res.json().get("id")
            logger.info(
                "Dataset '%s.%s' registered successfully with ID %s", schema, table_name, ds_id
            )
            return ds_id
        else:
            logger.warning(
                "Dataset registration response for '%s.%s': %s", schema, table_name, create_res.text
            )
            # Re-fetch in case of race condition or existing record
            re_res = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if re_res.status_code == 200:
                for ds in re_res.json().get("result", []):
                    if ds.get("table_name") == table_name and ds.get("schema") == schema:
                        return ds.get("id")
            return None

    def create_dashboard(self, dashboard_title: str) -> dict[str, Any] | None:
        """Create or find a Superset dashboard and configure embedded access."""
        url = f"{self.base_url}/api/v1/dashboard/"
        dash_id: int | None = None
        dash_uuid: str | None = None

        try:
            res = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if res.status_code == 200:
                for d in res.json().get("result", []):
                    if (
                        d.get("dashboard_title") == dashboard_title
                        or d.get("slug") == "transjakarta-transit-intelligence"
                    ):
                        dash_id = d.get("id")
                        # Fetch detailed dashboard to get UUID
                        d_res = self.session.get(f"{url}{dash_id}", timeout=REQUEST_TIMEOUT)
                        if d_res.status_code == 200:
                            dash_uuid = d_res.json().get("result", {}).get("uuid")
                        logger.info(
                            "Found existing dashboard '%s' (ID: %s, UUID: %s)",
                            dashboard_title,
                            dash_id,
                            dash_uuid,
                        )
                        break
        except Exception as e:
            logger.warning("Error searching dashboards: %s", e)

        if not dash_id:
            payload = {
                "dashboard_title": dashboard_title,
                "published": True,
                "slug": "transjakarta-transit-intelligence",
                "owners": [self.user_id],
                "position_json": "{}",
                "json_metadata": json.dumps({"expanded_slices": {}, "refresh_frequency": 0}),
            }
            create_res = self.session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
            if create_res.status_code in (200, 201):
                dash_id = create_res.json().get("id")
                d_res = self.session.get(f"{url}{dash_id}", timeout=REQUEST_TIMEOUT)
                if d_res.status_code == 200:
                    dash_uuid = d_res.json().get("result", {}).get("uuid")
                logger.info(
                    "Created dashboard '%s' (ID: %s, UUID: %s)", dashboard_title, dash_id, dash_uuid
                )
            else:
                logger.warning(
                    "Dashboard creation failed (HTTP %d): %s",
                    create_res.status_code,
                    create_res.text,
                )
                # Try without slug if slug conflict
                simple_payload = {
                    "dashboard_title": dashboard_title,
                    "published": True,
                    "owners": [self.user_id],
                }
                retry_res = self.session.post(url, json=simple_payload, timeout=REQUEST_TIMEOUT)
                if retry_res.status_code in (200, 201):
                    dash_id = retry_res.json().get("id")
                    d_res = self.session.get(f"{url}{dash_id}", timeout=REQUEST_TIMEOUT)
                    if d_res.status_code == 200:
                        dash_uuid = d_res.json().get("result", {}).get("uuid")
                    logger.info(
                        "Created dashboard without slug '%s' (ID: %s, UUID: %s)",
                        dashboard_title,
                        dash_id,
                        dash_uuid,
                    )

        if not dash_id:
            return None

        # Enable embedded dashboard
        embed_url = f"{self.base_url}/api/v1/dashboard/{dash_id}/embedded"
        embed_res = self.session.get(embed_url, timeout=REQUEST_TIMEOUT)
        embedded_uuid: str | None = None

        if embed_res.status_code == 200:
            embedded_uuid = embed_res.json().get("result", {}).get("uuid")
            logger.info(
                "Existing embedded dashboard configuration found (Embedded UUID: %s)", embedded_uuid
            )
        else:
            post_embed = self.session.post(
                embed_url, json={"allowed_domains": []}, timeout=REQUEST_TIMEOUT
            )
            if post_embed.status_code in (200, 201):
                embedded_uuid = post_embed.json().get("result", {}).get("uuid")
                logger.info(
                    "Embedded dashboard enabled successfully (Embedded UUID: %s)", embedded_uuid
                )
            else:
                logger.warning(
                    "Failed to enable embedded dashboard: (HTTP %d) %s",
                    post_embed.status_code,
                    post_embed.text,
                )

        return {
            "dashboard_id": dash_id,
            "dashboard_uuid": dash_uuid,
            "embedded_uuid": embedded_uuid,
        }

    def create_chart(
        self,
        dataset_id: int,
        slice_name: str,
        viz_type: str,
        params: dict[str, Any],
        dash_id: int | None = None,
    ) -> int | None:
        """Create an analytical chart in Superset."""
        url = f"{self.base_url}/api/v1/chart/"
        try:
            res = self.session.get(url, timeout=REQUEST_TIMEOUT)
            if res.status_code == 200:
                for ch in res.json().get("result", []):
                    if ch.get("slice_name") == slice_name:
                        ch_id = ch.get("id")
                        logger.info("Found existing chart '%s' (ID: %s)", slice_name, ch_id)
                        return ch_id
        except Exception as e:
            logger.warning("Error fetching charts: %s", e)

        payload = {
            "slice_name": slice_name,
            "datasource_id": dataset_id,
            "datasource_type": "table",
            "viz_type": viz_type,
            "params": json.dumps(params),
            "owners": [self.user_id],
            "dashboards": [dash_id] if dash_id else [],
        }
        create_res = self.session.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        if create_res.status_code in (200, 201):
            chart_id = create_res.json().get("id")
            logger.info("Chart '%s' created successfully with ID %s", slice_name, chart_id)
            return chart_id
        else:
            logger.warning(
                "Chart creation failed for '%s' (HTTP %d): %s",
                slice_name,
                create_res.status_code,
                create_res.text,
            )
            return None

    def run(self):
        """Execute full provisioning workflow."""
        if not self.wait_for_superset():
            return {"status": "SKIPPED", "reason": "Superset unavailable"}

        if not self.login():
            return {"status": "FAILED", "reason": "Authentication failure"}

        db_id = self.create_database_connection()
        if not db_id:
            return {"status": "FAILED", "reason": "Could not connect database"}

        # 1. Register conformed datasets
        fact_ds_id = self.create_dataset(db_id, "warehouse", "fact_taps")
        stops_ds_id = self.create_dataset(db_id, "warehouse", "dim_stops")
        routes_ds_id = self.create_dataset(db_id, "warehouse", "dim_routes")

        # 2. Create Dashboard First
        dash_info = self.create_dashboard("TransJakarta Transit Intelligence Overview")
        dash_id = dash_info.get("dashboard_id") if dash_info else None

        chart_ids = []
        if fact_ds_id:
            # Chart 1: Hourly Ridership Chart
            c1 = self.create_chart(
                dataset_id=fact_ds_id,
                slice_name="Hourly Tap-In Ridership Pattern",
                viz_type="echarts_timeseries_bar",
                params={
                    "datasource": f"{fact_ds_id}__table",
                    "metrics": ["count"],
                    "groupby": ["tap_type"],
                    "adhoc_filters": [
                        {
                            "clause": "WHERE",
                            "expressionType": "SQL",
                            "sqlExpression": "tap_type = 'IN'",
                        }
                    ],
                },
                dash_id=dash_id,
            )
            if c1:
                chart_ids.append(c1)

            # Chart 2: Card Bank Market Share
            c2 = self.create_chart(
                dataset_id=fact_ds_id,
                slice_name="Payment Card Issuer Distribution",
                viz_type="pie",
                params={
                    "datasource": f"{fact_ds_id}__table",
                    "metric": "count",
                    "groupby": ["pay_card_bank"],
                },
                dash_id=dash_id,
            )
            if c2:
                chart_ids.append(c2)

            # Chart 3: Top Boarding Stops
            c3 = self.create_chart(
                dataset_id=fact_ds_id,
                slice_name="Busiest Transit Boarding Stops",
                viz_type="table",
                params={
                    "datasource": f"{fact_ds_id}__table",
                    "metrics": ["count"],
                    "groupby": ["stop_id", "corridor_code"],
                    "order_desc": True,
                    "row_limit": 10,
                },
                dash_id=dash_id,
            )
            if c3:
                chart_ids.append(c3)

            # Chart 4: Ridership by Direction and Corridor
            c4 = self.create_chart(
                dataset_id=fact_ds_id,
                slice_name="Ridership by Direction and Corridor",
                viz_type="echarts_timeseries_bar",
                params={
                    "datasource": f"{fact_ds_id}__table",
                    "metrics": ["count"],
                    "groupby": ["corridor_code"],
                    "row_limit": 15,
                },
                dash_id=dash_id,
            )
            if c4:
                chart_ids.append(c4)

        if stops_ds_id:
            # Chart 5: Geospatial Transit Stop Network Map (deck.gl Scatterplot)
            c5 = self.create_chart(
                dataset_id=stops_ds_id,
                slice_name="TransJakarta Stop Network Map",
                viz_type="deck_scatter",
                params={
                    "datasource": f"{stops_ds_id}__table",
                    "spatial": {
                        "type": "latlong",
                        "latCol": "latitude",
                        "lonCol": "longitude",
                    },
                    "row_limit": 10000,
                    "mapbox_style": "mapbox://styles/mapbox/streets-v9",
                    "viewport": {
                        "longitude": 106.82715,
                        "latitude": -6.17539,
                        "zoom": 11,
                        "bearing": 0,
                        "pitch": 0,
                    },
                    "point_radius_fixed": {"type": "fix", "value": 25},
                    "point_unit": "square_meters",
                    "min_radius": 2,
                    "max_radius": 250,
                    "color_picker": {"r": 0, "g": 86, "b": 150, "a": 1},
                    "tooltip": "<b>Stop Name:</b> {stop_name}<br><b>Stop ID:</b> {stop_id}",
                },
                dash_id=dash_id,
            )
            if c5:
                chart_ids.append(c5)

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
