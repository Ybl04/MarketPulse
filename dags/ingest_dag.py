from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator
from app.scripts.ingest import run
import datetime
import os


default_args = {
    'owner': 'data_team',
    'start_date': datetime.datetime(2026, 7, 1),
    'retries': 1,
    'retry_delay': datetime.timedelta(minutes=5),
    'email_on_failure': True,
    'email': ['ybelfalah14@gmail.com'],
}

with DAG(
    dag_id = "marketpulse_ingest",
    default_args = default_args,
    schedule = "0 7 * * *",
    catchup = False,
) as dag:
    trigger_ingestion_task = PythonOperator(
        task_id="run_ingestion",
        python_callable=run
    ) 

    run_dbt_task = DockerOperator(
        task_id="run_dbt_build",
        image="marketpulse-dbt",
        command="dbt build --profiles-dir /opt/dbt/marketpulse_dbt --project-dir /opt/dbt/marketpulse_dbt",
        network_mode="marketpulse_default",
        auto_remove=True,
        docker_url="tcp://docker-proxy:2375",
        force_pull=False,
        mount_tmp_dir=False,
        environment={
        "POSTGRES_USER": os.environ.get("POSTGRES_USER"),
        "POSTGRES_PASSWORD": os.environ.get("POSTGRES_PASSWORD"),
        "POSTGRES_DB": os.environ.get("POSTGRES_DB"),
        "POSTGRES_HOST": "db",
        },
    )


    trigger_ingestion_task >> run_dbt_task

    
