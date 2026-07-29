from airflow import DAG
from airflow.operators.python import PythonOperator
from app.scripts.ingest import run
import datetime



default_args = {
    'owner': 'data_team',
    'start_date': datetime.datetime(2026, 7, 1),
    'retries': 1,
    'retry_delay': datetime.timedelta(minutes=5),
    'email_on_failure': True,
    'email': [''],
}

with DAG(
    dag_id = "marketpulse_ingest",
    default_args = default_args,
    schedule = "0 7 * * *",
    catchup = False,
) as dag:
    trriger_ingestion_task = PythonOperator(
        task_id="run_ingestion",
        python_callable=run
    ) 
    
