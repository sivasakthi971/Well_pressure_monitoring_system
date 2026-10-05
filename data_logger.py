import csv
import json
import os
import sqlite3
from datetime import datetime
import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
DATA_DIR = os.getenv("DATA_DIR", ".")

CSV_FILE = os.path.join(DATA_DIR, "pressure_data.csv")
DB_FILE = os.path.join(DATA_DIR, "well_integrity.db")

LIMITS = {
    "tubing_head": 148.0,
    "casing_A": 110.0,
    "casing_B": 95.0,
    "casing_C": 85.0,
    "flowline": 100.0,
    "choke": 90.0
}


def init_storage():
    if DATA_DIR and DATA_DIR != "." and not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR, exist_ok=True)

    # Initialize CSV
    if not os.path.exists(CSV_FILE):
        with open(CSV_FILE, "w", newline="") as file:
            writer = csv.writer(file)
            writer.writerow([
                "timestamp",
                "well_id",
                "tubing_head",
                "casing_A",
                "casing_B",
                "casing_C",
                "flowline",
                "choke",
                "alarm"
            ])

    # Initialize SQLite Database
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS telemetry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            well_id TEXT,
            tubing_head REAL,
            casing_A REAL,
            casing_B REAL,
            casing_C REAL,
            flowline REAL,
            choke REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alarms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            well_id TEXT,
            sensor TEXT,
            alarm_class TEXT,
            severity TEXT,
            message TEXT,
            suppressed INTEGER
        )
    """)
    conn.commit()
    conn.close()


def log_telemetry_and_alarms(data):
    timestamp = data.get("timestamp", datetime.now().isoformat())
    well_id = data.get("well_id", "WELL-001")
    t_head = data.get("tubing_head", 0.0)
    c_a = data.get("casing_A", 0.0)
    c_b = data.get("casing_B", 0.0)
    c_c = data.get("casing_C", 0.0)
    flowline = data.get("flowline", 0.0)
    choke = data.get("choke", 0.0)

    # Determine basic alarm state for CSV backward compatibility
    alarm = "NO ALARM"
    for sensor, limit in LIMITS.items():
        val = data.get(sensor)
        if val is not None and val > limit:
            alarm = f"HIGH PRESSURE: {sensor}"

    # 1. Write to CSV
    with open(CSV_FILE, "a", newline="") as file:
        writer = csv.writer(file)
        writer.writerow([timestamp, well_id, t_head, c_a, c_b, c_c, flowline, choke, alarm])

    # 2. Write to SQLite
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO telemetry (timestamp, well_id, tubing_head, casing_A, casing_B, casing_C, flowline, choke)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (timestamp, well_id, t_head, c_a, c_b, c_c, flowline, choke))

    # Log Alarms into DB if thresholds exceeded
    if c_a > 110.0:
        cursor.execute("""
            INSERT INTO alarms (timestamp, well_id, sensor, alarm_class, severity, message, suppressed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, well_id, "casing_A", "MAASP_EXCEEDED_SCP", "CRITICAL", f"SCP MAASP Exceeded on Casing A ({c_a:.2f} bar)", 0))

    if flowline < 35.0:
        cursor.execute("""
            INSERT INTO alarms (timestamp, well_id, sensor, alarm_class, severity, message, suppressed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (timestamp, well_id, "flowline", "PRODUCTION_LOSS_SIGNAL", "WARNING", f"Hydrate/Blockage Risk on Flowline ({flowline:.2f} bar)", 0))

    conn.commit()
    conn.close()

    print(f"Logged [{well_id}]: {timestamp} | Alarm: {alarm}")


def on_connect(client, userdata, flags, reason_code, properties):
    print("Connected to MQTT Broker:", MQTT_BROKER)
    print("Logging multi-well pressure telemetry to CSV and SQLite DB...")
    client.subscribe("well/+/pressure")
    client.subscribe("well/WELL-001/pressure")


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        log_telemetry_and_alarms(data)
    except Exception as error:
        print("Logging error:", error)


init_storage()

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

print("Starting Enterprise Data Logger...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_forever()