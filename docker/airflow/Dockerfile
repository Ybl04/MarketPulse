FROM apache/airflow:2.8.1-python3.10

COPY . /opt/airflow/marketpulse
RUN pip install -r /opt/airflow/marketpulse/requirements-airflow.txt
ENV PYTHONPATH="/opt/airflow/marketpulse:${PYTHONPATH}"