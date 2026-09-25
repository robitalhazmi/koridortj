"""Unit tests for Airflow DAG structure, integrity, and cycle validation."""

import pytest


# Test DAG definitions
def test_gtfs_ingest_dag_structure():
    """Verify gtfs_ingest DAG loads without syntax error and has expected task flow."""
    # Mock airflow imports if not in environment or test directly
    try:
        from airflow.models import DagBag

        dagbag = DagBag(dag_folder="dags", include_examples=False)
        assert len(dagbag.import_errors) == 0, f"DAG import errors: {dagbag.import_errors}"

        dag = dagbag.get_dag("gtfs_ingest")
        assert dag is not None
        assert dag.schedule_interval == "0 3 * * 1"
        assert len(dag.tasks) == 3
        task_ids = [t.task_id for t in dag.tasks]
        assert "check_feed_availability" in task_ids
        assert "ingest_gtfs_data" in task_ids
        assert "verify_row_counts" in task_ids
    except ImportError:
        pytest.skip(
            "Airflow not installed in host test environment; tested inside Airflow container"
        )


def test_warehouse_build_dag_structure():
    """Verify warehouse_build DAG loads without syntax error and has expected task flow."""
    try:
        from airflow.models import DagBag

        dagbag = DagBag(dag_folder="dags", include_examples=False)
        assert len(dagbag.import_errors) == 0, f"DAG import errors: {dagbag.import_errors}"

        dag = dagbag.get_dag("warehouse_build")
        assert dag is not None
        assert dag.schedule_interval == "0 4 * * *"
        assert len(dag.tasks) == 5
        task_ids = [t.task_id for t in dag.tasks]
        assert "dbt_debug_connection" in task_ids
        assert "dbt_run_staging" in task_ids
        assert "dbt_run_warehouse" in task_ids
        assert "dbt_test_quality_gate" in task_ids
        assert "dbt_generate_docs" in task_ids
    except ImportError:
        pytest.skip(
            "Airflow not installed in host test environment; tested inside Airflow container"
        )
