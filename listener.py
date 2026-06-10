import csv
import json
from fastapi import FastAPI, Request, WebSocket
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime
import threading
import math
import time

app = FastAPI()

# State
recording = False
current_label = None
session_id = 0
buffer = []
lock = threading.Lock()

gesture_active = False
gesture_peak_sample = None

last_gesture_time = 0
COOLDOWN = 0.1

ACCEL_THRESHOLD = 12
GYRO_THRESHOLD = 4

# Data
class Sensor(BaseModel):
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float

class IMUData(BaseModel):
    timestamp: int
    sensor: Sensor


def build_row(timestamp: int, sensor: Dict[str, Any]):
    accel_x = sensor["accel_x"]
    accel_y = sensor["accel_y"]
    accel_z = sensor["accel_z"]
    gyro_x = sensor["gyro_x"]
    gyro_y = sensor["gyro_y"]
    gyro_z = sensor["gyro_z"]

    return [
        datetime.now().isoformat(),
        timestamp,
        accel_x,
        accel_y,
        accel_z,
        gyro_x,
        gyro_y,
        gyro_z,
        (accel_x**2 + accel_y**2 + accel_z**2) ** 0.5,
        (gyro_x**2 + gyro_y**2 + gyro_z**2) ** 0.5,
    ]


def start_recording(label: str):
    global recording, current_label, session_id, buffer, last_gesture_time, gesture_active, gesture_peak_sample

    if recording:
        return {"status": "already recording"}

    current_label = label
    recording = True
    buffer = []
    gesture_active = False
    gesture_peak_sample = None

    last_gesture_time = 0
    session_id += 1

    print("Starting recording")

    return {
        "status": "started",
        "label": label,
        "session_id": session_id,
    }


def process_imu(timestamp: int, sensor: Dict[str, Any]):
    global recording, buffer, last_gesture_time

    if not recording:
        return {"status": "not recording"}

    row = build_row(timestamp, sensor)

    with lock:
        buffer.append(row)

    ax = sensor["accel_x"]
    ay = sensor["accel_y"]
    az = sensor["accel_z"]

    gx = sensor["gyro_x"]
    gy = sensor["gyro_y"]
    gz = sensor["gyro_z"]

    gyro_mag = (gx**2 + gy**2 + gz**2) ** 0.5

    current_time = time.time()

    print("Received IMU data")

    gesture = classify_flick(sensor)
    if gesture:
        print(f"Detected gesture: {gesture}")

    return {"status": "data received"}


def save_recording():
    global recording, buffer, current_label, session_id

    if not recording:
        return {"status": "not recording"}

    filename = f"{current_label}_{session_id}.csv"

    headers = [
        "received_at",
        "timestamp",
        "accel_x",
        "accel_y",
        "accel_z",
        "gyro_x",
        "gyro_y",
        "gyro_z",
        "accel_mag",
        "gyro_mag"
    ]

    with open(filename, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(buffer)

    recording = False
    buffer = []

    print(f"Saved recording to {filename}")

    return {
        "status": "saved",
        "file": filename,
    }

@app.websocket("/ws")
async def ws(websocket: WebSocket):
    await websocket.accept()

    while True:
        msg = await websocket.receive_text()        

        try:
            payload = json.loads(msg)
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            print(f"Skipping malformed websocket payload: {error}")
            continue

        msg_type = payload.get("type")

        if msg_type == "control":
            action = payload.get("action")

            if action == "start":
                label = payload.get("label")
                if not label:
                    await websocket.send_text(json.dumps({"status": "error", "message": "missing label"}))
                    continue

                await websocket.send_text(json.dumps(start_recording(label)))
                continue

            if action in {"stop", "save"}:
                await websocket.send_text(json.dumps(save_recording()))
                continue

            await websocket.send_text(json.dumps({"status": "error", "message": "unknown control action"}))
            continue

        if msg_type == "imu":
            sensor = payload.get("sensor")
            timestamp = payload.get("timestamp")

            if sensor is None or timestamp is None:
                await websocket.send_text(json.dumps({"status": "error", "message": "missing imu fields"}))
                continue

            await websocket.send_text(json.dumps(process_imu(timestamp, sensor)))
            continue

        await websocket.send_text(json.dumps({"status": "error", "message": "unknown message type"}))


def classify_gesture_from_peak(sensor: Dict[str, Any]):
    gx = sensor["gyro_x"]
    gy = sensor["gyro_y"]
    gz = sensor["gyro_z"]

    abs_x = abs(gx)
    abs_y = abs(gy)
    abs_z = abs(gz)

    if abs_x >= abs_y and abs_x >= abs_z:
        return "UP" if gx > 0 else "DOWN"

    if abs_z >= abs_x and abs_z >= abs_y:
        return "RIGHT" if gz > 0 else "LEFT"

    return None

def classify_flick(sensor: Dict[str, Any]):
    global gesture_active, gesture_peak_sample, last_gesture_time

    gyro_mag = (
        sensor["gyro_x"] ** 2
        + sensor["gyro_y"] ** 2
        + sensor["gyro_z"] ** 2
    ) ** 0.5

    current_time = time.time()

    if gyro_mag > GYRO_THRESHOLD:
        if current_time - last_gesture_time < COOLDOWN:
            return None

        if not gesture_active:
            gesture_active = True
            gesture_peak_sample = dict(sensor)
            return None

        if gesture_peak_sample is None:
            gesture_peak_sample = dict(sensor)
        else:
            peak_mag = (
                gesture_peak_sample["gyro_x"] ** 2
                + gesture_peak_sample["gyro_y"] ** 2
                + gesture_peak_sample["gyro_z"] ** 2
            ) ** 0.5
            if gyro_mag > peak_mag:
                gesture_peak_sample = dict(sensor)

        return None

    if not gesture_active:
        return None

    gesture_active = False

    peak_sample = gesture_peak_sample
    gesture_peak_sample = None

    if peak_sample is None:
        return None

    if current_time - last_gesture_time < COOLDOWN:
        return None

    label = classify_gesture_from_peak(peak_sample)
    if label:
        last_gesture_time = current_time
    return label

@app.get("/")
def root():
    return {"message": "IMU Data Listener is running."}