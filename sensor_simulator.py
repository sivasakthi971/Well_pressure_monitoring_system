import os
import sys
import json
import random
import time
import yaml
from datetime import datetime

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
REGISTER_FILE = os.getenv("WELL_REGISTER", "well_register.yaml")

# Load well register if available
wells_config = {}
if os.path.exists(REGISTER_FILE):
    with open(REGISTER_FILE, "r") as f:
        wells_config = yaml.safe_load(f).get("wells", {})

if not wells_config:
    wells_config = {
        "WELL-001": {
            "name": "Alpha Well-001",
            "normal_band": {
                "tubing_head": [115.0, 135.0],
                "casing_A": [90.0, 105.0],
                "casing_B": [80.0, 95.0],
                "casing_C": [70.0, 85.0],
                "flowline": [55.0, 75.0],
                "choke": [50.0, 70.0]
            }
        },
        "WELL-002": {
            "name": "Beta Well-002 (SCP Risk)",
            "normal_band": {
                "tubing_head": [110.0, 130.0],
                "casing_A": [85.0, 100.0],
                "casing_B": [75.0, 88.0],
                "casing_C": [65.0, 78.0],
                "flowline": [50.0, 70.0],
                "choke": [45.0, 65.0]
            }
        },
        "WELL-003": {
            "name": "Gamma Well-003 (Hydrate Risk)",
            "normal_band": {
                "tubing_head": [120.0, 140.0],
                "casing_A": [92.0, 108.0],
                "casing_B": [82.0, 96.0],
                "casing_C": [70.0, 82.0],
                "flowline": [58.0, 78.0],
                "choke": [52.0, 72.0]
            }
        }
    }

# Initialize live telemetry state per well
well_states = {}
for well_id, config in wells_config.items():
    band = config.get("normal_band", {})
    well_states[well_id] = {
        "tubing_head": (band.get("tubing_head", [115, 135])[0] + band.get("tubing_head", [115, 135])[1]) / 2,
        "casing_A": (band.get("casing_A", [90, 105])[0] + band.get("casing_A", [90, 105])[1]) / 2,
        "casing_B": (band.get("casing_B", [80, 95])[0] + band.get("casing_B", [80, 95])[1]) / 2,
        "casing_C": (band.get("casing_C", [70, 85])[0] + band.get("casing_C", [70, 85])[1]) / 2,
        "flowline": (band.get("flowline", [55, 75])[0] + band.get("flowline", [55, 75])[1]) / 2,
        "choke": (band.get("choke", [50, 70])[0] + band.get("choke", [50, 70])[1]) / 2,
    }

def update_sensor(val, min_val, max_val):
    change = random.uniform(-2.5, 2.5)
    new_val = val + change
    if new_val <= min_val:
        new_val = val + random.uniform(1.0, 2.5)
    elif new_val >= max_val:
        new_val = val - random.uniform(1.0, 2.5)
    return round(new_val, 2)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.connect(MQTT_BROKER, MQTT_PORT, 60)

print("==============================================")
print("MULTI-WELL INTEGRITY & SENSOR SIMULATOR")
print("==============================================")
print(f"Connected to MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
print("Simulating stock wells:", list(well_states.keys()))
print("Press Ctrl+C to stop\n")

counter = 0

try:
    while True:
        counter += 1

        for well_id, pressures in well_states.items():
            band = wells_config[well_id].get("normal_band", {})

            for sensor in pressures:
                min_val, max_val = band.get(sensor, (50.0, 150.0))
                pressures[sensor] = update_sensor(pressures[sensor], min_val, max_val)

            operator_action = None

            # ----------------------------------------------------
            # Scenario Injections for Realistic Field Simulation
            # ----------------------------------------------------
            
            # Scenario 1: WELL-002 Sustained Casing Pressure (SCP) build-up
            if well_id == "WELL-002" and counter % 6 == 0:
                pressures["casing_A"] = round(pressures["casing_A"] + random.uniform(8.0, 15.0), 2)
                print(f"⚠️ [WELL-002] Sustained Casing Pressure (SCP) Build-up: casing_A = {pressures['casing_A']} bar")

            # Scenario 2: WELL-003 Hydrate / Blockage Formation (Flowline Pressure Drop)
            if well_id == "WELL-003" and counter % 8 == 0:
                pressures["flowline"] = round(max(15.0, pressures["flowline"] - random.uniform(10.0, 20.0)), 2)
                print(f"⚠️ [WELL-003] Blockage/Hydrate Signal: flowline = {pressures['flowline']} bar")

            # Scenario 3: WELL-001 Deliberate Choke Adjustment by Operator
            if well_id == "WELL-001" and counter % 10 == 0:
                operator_action = "CHOKE_ADJUSTMENT"
                pressures["tubing_head"] = round(pressures["tubing_head"] - 12.0, 2)
                print(f"🔧 [WELL-001] Operator Action Triggered: CHOKE_ADJUSTMENT")

            # Scenario 4: Stuck Sensor Fault simulation (WELL-001 choke sensor constant)
            if well_id == "WELL-001" and counter % 15 == 0:
                pressures["choke"] = 58.50  # Constant reading to trigger stuck sensor check

            payload = {
                "well_id": well_id,
                "timestamp": datetime.now().isoformat(),
                "tubing_head": pressures["tubing_head"],
                "casing_A": pressures["casing_A"],
                "casing_B": pressures["casing_B"],
                "casing_C": pressures["casing_C"],
                "flowline": pressures["flowline"],
                "choke": pressures["choke"],
                "unit": "bar"
            }

            if operator_action:
                payload["operator_action"] = operator_action

            message = json.dumps(payload)

            # Publish to specific well topic and generic topic for WELL-001
            topic = f"well/{well_id}/pressure"
            client.publish(topic, message)

            if well_id == "WELL-001":
                client.publish("well/WELL-001/pressure", message)

            print(f"Published [{topic}]: {message}")

        print("-" * 65)
        time.sleep(3)

except KeyboardInterrupt:
    print("\nSimulator stopped.")
finally:
    client.disconnect()