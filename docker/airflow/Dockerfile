FROM apache/airflow:2.8.1-python3.10

USER root
RUN apt-get update && apt-get install -y curl ca-certificates && \
    curl -sL https://aka.ms/InstallAzureCLIDeb | bash && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

USER airflow

COPY . /opt/airflow/marketpulse
COPY ./dags /opt/airflow/dags
COPY init_airflow.sh /opt/airflow/init_airflow.sh

RUN pip install -r /opt/airflow/marketpulse/requirements-airflow.txt
ENV PYTHONPATH="/opt/airflow/marketpulse:${PYTHONPATH}"