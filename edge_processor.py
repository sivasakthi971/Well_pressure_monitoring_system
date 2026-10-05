import json
import os
import time
import yaml
from collections import defaultdict, deque
import paho.mqtt.client as mqtt

MQTT_BROKER = os.getenv("MQTT_BROKER", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
REGISTER_FILE = os.getenv("WELL_REGISTER", "well_register.yaml")

# Load per-well YAML register
wells_register = {}
if os.path.exists(REGISTER_FILE):
    with open(REGISTER_FILE, "r") as f:
        wells_register = yaml.safe_load(f).get("wells", {})

# Fallback default limits
DEFAULT_MAASP = {
    "casing_A": 110.0,
    "casing_B": 95.0,
    "casing_C": 85.0
}
DEFAULT_TUBING_THRESHOLDS = {
    "HIHI": 145.0,
    "HI": 135.0,
    "LO": 90.0,
    "LOLO": 80.0
}

# Rolling telemetry buffer for dP/dt calculation & stuck sensor detection
telemetry_history = defaultdict(lambda: defaultdict(lambda: deque(maxlen=5)))
previous_timestamps = defaultdict(dict)


def load_well_config(well_id):
    if well_id in wells_register:
        return wells_register[well_id]
    return {
        "maasp": DEFAULT_MAASP,
        "tubing_maop": 145.0,
        "tubing_thresholds": DEFAULT_TUBING_THRESHOLDS,
        "max_buildup_rate_bar_hr": 2.5
    }


def evaluate_integrity_rules(data):
    well_id = data.get("well_id", "WELL-001")
    timestamp = data.get("timestamp")
    config = load_well_config(well_id)
    
    maasp = config.get("maasp", DEFAULT_MAASP)
    tubing_limits = config.get("tubing_thresholds", DEFAULT_TUBING_THRESHOLDS)
    max_buildup_rate = config.get("max_buildup_rate_bar_hr", 2.5)
    
    alarms = []
    sensors = ["tubing_head", "casing_A", "casing_B", "casing_C", "flowline", "choke"]

    # Check for deliberate operator action (e.g. choke change)
    is_operator_action = data.get("operator_action") == "CHOKE_ADJUSTMENT"

    for sensor in sensors:
        val = data.get(sensor)
        if val is None:
            continue

        # --------------------------------------------------------
        # 1. Telemetry Validation (Stuck, Range, Drift)
        # --------------------------------------------------------
        if val < 0 or val > 250.0:
            alarms.append({
                "sensor": sensor,
                "alarm_class": "INSTRUMENT_FAULT",
                "severity": "WARNING",
                "message": f"OUT OF RANGE: {val:.2f} bar"
            })
            continue

        history = telemetry_history[well_id][sensor]
        history.append(val)

        # Check for Stuck Sensor (zero variance over last 5 readings)
        if len(history) == 5 and len(set(history)) == 1:
            alarms.append({
                "sensor": sensor,
                "alarm_class": "INSTRUMENT_FAULT",
                "severity": "WARNING",
                "message": f"STUCK SENSOR FAULT: Constant value {val:.2f} bar"
            })

    # --------------------------------------------------------
    # 2. Tubing Pressure Rules (HIHI / HI / LO / LOLO)
    # --------------------------------------------------------
    tubing_val = data.get("tubing_head")
    if tubing_val is not None:
        if tubing_val >= tubing_limits.get("HIHI", 148.0):
            alarm_obj = {
                "sensor": "tubing_head",
                "alarm_class": "TUBING_INTEGRITY",
                "severity": "CRITICAL",
                "message": f"TUBING HIHI ALARM: {tubing_val:.2f} bar >= {tubing_limits['HIHI']} bar"
            }
            if is_operator_action:
                alarm_obj["suppressed"] = True
                alarm_obj["suppress_reason"] = "Operator deliberate choke adjustment"
            alarms.append(alarm_obj)

        elif tubing_val >= tubing_limits.get("HI", 138.0):
            alarms.append({
                "sensor": "tubing_head",
                "alarm_class": "TUBING_INTEGRITY",
                "severity": "WARNING",
                "message": f"TUBING HI ALARM: {tubing_val:.2f} bar >= {tubing_limits['HI']} bar"
            })

        elif tubing_val <= tubing_limits.get("LOLO", 80.0):
            alarms.append({
                "sensor": "tubing_head",
                "alarm_class": "TUBING_INTEGRITY",
                "severity": "CRITICAL",
                "message": f"TUBING LOLO ALARM: {tubing_val:.2f} bar <= {tubing_limits['LOLO']} bar"
            })

        elif tubing_val <= tubing_limits.get("LO", 90.0):
            alarms.append({
                "sensor": "tubing_head",
                "alarm_class": "TUBING_INTEGRITY",
                "severity": "WARNING",
                "message": f"TUBING LO ALARM: {tubing_val:.2f} bar <= {tubing_limits['LO']} bar"
            })

    # --------------------------------------------------------
    # 3. Annulus MAASP & Sustained Casing Pressure (SCP) Rules
    # --------------------------------------------------------
    for ann in ["casing_A", "casing_B", "casing_C"]:
        ann_val = data.get(ann)
        limit = maasp.get(ann)
        if ann_val is not None and limit is not None:
            if ann_val > limit:
                alarms.append({
                    "sensor": ann,
                    "alarm_class": "MAASP_EXCEEDED_SCP",
                    "severity": "CRITICAL",
                    "message": f"SCP MAASP EXCEEDED: {ann} = {ann_val:.2f} bar > MAASP ({limit:.0f} bar)"
                })

            # Calculate dP/dt rate of change
            hist = telemetry_history[well_id][ann]
            if len(hist) >= 2:
                dp = hist[-1] - hist[0]
                # If dP/dt rate of build-up is abnormally fast
                if dp > max_buildup_rate:
                    alarms.append({
                        "sensor": ann,
                        "alarm_class": "ABNORMAL_BUILDUP_RATE",
                        "severity": "CRITICAL",
                        "message": f"HIGH BUILD-UP RATE (SCP): +{dp:.2f} bar buildup rate > limit ({max_buildup_rate:.1f} bar/hr)"
                    })

    # --------------------------------------------------------
    # 4. Production Loss Signals (Blockage, Sand-up, Hydrates)
    # --------------------------------------------------------
    flowline_val = data.get("flowline")
    choke_val = data.get("choke")
    if flowline_val is not None and choke_val is not None:
        # Unexpected drop in flowline pressure relative to choke indicates blockage or hydrate formation
        if (choke_val - flowline_val) > 25.0 or flowline_val < 35.0:
            alarms.append({
                "sensor": "flowline",
                "alarm_class": "PRODUCTION_LOSS_SIGNAL",
                "severity": "WARNING",
                "message": f"HYDRATE / BLOCKAGE DETECTED: Flowline pressure dropped to {flowline_val:.2f} bar"
            })

    return alarms


def on_connect(client, userdata, flags, reason_code, properties):
    print("==================================================")
    print("WELL INTEGRITY & PRODUCTION EDGE MONITOR")
    print("==================================================")
    print("Connected to MQTT Broker:", MQTT_BROKER)
    print("Subscribing to telemetry topics: well/+/pressure")
    client.subscribe("well/+/pressure")
    client.subscribe("well/WELL-001/pressure")


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        well_id = data.get("well_id", "UNKNOWN")
        timestamp = data.get("timestamp", "N/A")

        alarms = evaluate_integrity_rules(data)

        print(f"\n[{timestamp}] Telemetry Received for Well: {well_id}")
        for s in ["tubing_head", "casing_A", "casing_B", "casing_C", "flowline", "choke"]:
            if data.get(s) is not None:
                print(f"  {s:15}: {data[s]:7.2f} bar")

        if not alarms:
            print("  STATUS          : ✅ NORMAL (All parameters within MAASP & MAOP envelope)")
        else:
            print("  ALARMS DETECTED :")
            for a in alarms:
                supp_str = " (SUPPRESSED - Operator Action)" if a.get("suppressed") else ""
                print(f"    🚨 [{a['severity']}] [{a['alarm_class']}] {a['sensor']}: {a['message']}{supp_str}")

    except Exception as error:
        print("Processing error:", error)


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message

print("Starting Enterprise Edge Processor...")
client.connect(MQTT_BROKER, MQTT_PORT, 60)
client.loop_forever()