FROM apache/airflow:2.8.1

# Copy the project code into the container
COPY . /opt/airflow/marketpulse

# Install project's dependencies
RUN pip install --no-cache-dir -r /opt/airflow/marketpulse/requirements-app.txt

# Tell Python where to find the app/ module
ENV PYTHONPATH="/opt/airflow/marketpulse:${PYTHONPATH}"