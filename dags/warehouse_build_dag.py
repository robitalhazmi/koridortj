"""Airflow DAG: Nightly Warehouse Build and dbt Quality Gate.

Executes dbt staging views, builds the star schema warehouse models (dim/fact),
enforces automated data quality assertions (dbt test), and updates documentation.
"""

from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.bash import BashOperator

DBT_PROJECT_DIR = "/opt/airflow/dbt"
DBT_PROFILES_DIR = "/opt/airflow/dbt"

default_args = {
    "owner": "koridortj",
    "depends_on_past": False,
    "email_on_failure": False,
    "email_on_retry": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=2),
}

with DAG(
    dag_id="warehouse_build",
    default_args=default_args,
    description="Nightly dbt warehouse build, star schema transformation, and quality testing",
    schedule_interval="0 4 * * *",  # Daily at 04:00 UTC
    start_date=datetime(2023, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["transjakarta", "dbt", "warehouse", "star_schema", "data_quality"],
) as dag:

    task_dbt_debug = BashOperator(
        task_id="dbt_debug_connection",
        bash_command=f"dbt parse --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROFILES_DIR}",
    )

    task_dbt_run_staging = BashOperator(
        task_id="dbt_run_staging",
        bash_command=f"dbt run --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROFILES_DIR} --select staging",
    )

    task_dbt_run_warehouse = BashOperator(
        task_id="dbt_run_warehouse",
        bash_command=f"dbt run --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROFILES_DIR} --select warehouse",
    )

    task_dbt_test = BashOperator(
        task_id="dbt_test_quality_gate",
        bash_command=f"dbt test --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROFILES_DIR}",
    )

    task_dbt_docs = BashOperator(
        task_id="dbt_generate_docs",
        bash_command=f"dbt docs generate --project-dir {DBT_PROJECT_DIR} --profiles-dir {DBT_PROFILES_DIR}",
    )

    task_dbt_debug >> task_dbt_run_staging >> task_dbt_run_warehouse >> task_dbt_test >> task_dbt_docs
