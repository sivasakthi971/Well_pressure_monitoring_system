FROM python:3.12-slim

WORKDIR /app

# Install Mosquitto MQTT broker and Supervisor process manager
RUN apt-get update \
    && apt-get install -y --no-install-recommends mosquitto supervisor \
    && rm -rf /var/lib/apt/lists/*

# Install all Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create storage directory for database and CSV logs
RUN mkdir -p /app/data

# Copy application files and configs
COPY well_register.yaml .
COPY sensor_simulator.py .
COPY edge_processor.py .
COPY data_logger.py .
COPY dashboard.py .
COPY mosquitto/mosquitto.conf ./mosquitto.conf
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# Expose Streamlit dashboard (8501) and MQTT broker (1883)
EXPOSE 8501 1883

# Default environment variables
ENV MQTT_BROKER=127.0.0.1 \
    MQTT_PORT=1883 \
    DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1

# Run supervisor to orchestrate all services concurrently
CMD ["supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]