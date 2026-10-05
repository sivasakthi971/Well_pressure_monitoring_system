#!/bin/sh
set -e

mkdir -p /app/data

mosquitto -c /app/mosquitto.conf &
MOSQ_PID=$!

sleep 2

export MQTT_BROKER=127.0.0.1
export MQTT_PORT=1883
export DATA_DIR=/app/data
export PYTHONUNBUFFERED=1

python -u /app/sensor_simulator.py &
SENSOR_PID=$!

python -u /app/edge_processor.py &
PROCESSOR_PID=$!

python -u /app/data_logger.py &
LOGGER_PID=$!

python -m streamlit run /app/dashboard.py --server.address=0.0.0.0 --server.port=8501 &
DASHBOARD_PID=$!

trap 'kill $MOSQ_PID $SENSOR_PID $PROCESSOR_PID $LOGGER_PID $DASHBOARD_PID 2>/dev/null || true' INT TERM EXIT

wait
