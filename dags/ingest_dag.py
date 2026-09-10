from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
from app.scripts.ingest import run
import datetime

default_args = {
    'owner': 'data_team',
    'start_date': datetime.datetime(2026, 7, 1),
    'retries': 1,
    'retry_delay': datetime.timedelta(minutes=5),
    'email_on_failure': True,
    'email': ['ybelfalah14@gmail.com'],
}

DBT_JOB_COMMAND = """
az login --identity && \
EXECUTION=$(az containerapp job start \
  --name marketpulse-dbt-job \
  --resource-group marketpulse-rg \
  --query "name" -o tsv) && \
echo "Job execution started: $EXECUTION" && \
while true; do
  STATUS=$(az containerapp job execution show \
    --name marketpulse-dbt-job \
    --resource-group marketpulse-rg \
    --job-execution-name $EXECUTION \
    --query "properties.status" -o tsv)
  echo "Current status: $STATUS"
  if [ "$STATUS" = "Succeeded" ]; then exit 0; fi
  if [ "$STATUS" = "Failed" ]; then exit 1; fi
  sleep 15
done
"""

with DAG(
    dag_id="marketpulse_ingest",
    default_args=default_args,
    schedule="0 7 * * *",
    catchup=False,
) as dag:

    trigger_ingestion_task = PythonOperator(
        task_id="run_ingestion",
        python_callable=run
    )

    run_dbt_task = BashOperator(
        task_id="run_dbt_build",
        bash_command=DBT_JOB_COMMAND,
    )

    trigger_ingestion_task >> run_dbt_task