import csv
import json
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime
import threading
import math
from collections import deque

app = FastAPI()

# State
recording = False
current_label = None
session_id = 0
buffer = []
lock = threading.Lock()

# Gesture classification state
WINDOW_SIZE = 10  # ~500ms at 50ms samples
gyro_window = deque(maxlen=WINDOW_SIZE)
accel_window = deque(maxlen=WINDOW_SIZE)
gesture_in_progress = False
peak_gyro_x = 0
peak_gyro_y = 0
peak_gyro_z = 0
gesture_sample_count = 0

# Thresholds
GYRO_MOTION_THRESHOLD = 2.0
GYRO_PEAK_MIN = 4.0

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
    global recording, current_label, session_id, buffer

    if recording:
        return {"status": "already recording"}

    current_label = label
    recording = True
    buffer = []
    session_id += 1

    print("Starting recording")

    return {
        "status": "started",
        "label": label,
        "session_id": session_id,
    }


def classify_gesture_peak():
    """Classify based on which axis had the peak gyro value."""
    abs_x = abs(peak_gyro_x)
    abs_y = abs(peak_gyro_y)
    abs_z = abs(peak_gyro_z)
    
    # Determine which axis dominated
    if abs_x >= abs_y and abs_x >= abs_z:
        return "DOWN" if peak_gyro_x < 0 else "UP"
    elif abs_z >= abs_x and abs_z >= abs_y:
        return "RIGHT" if peak_gyro_z > 0 else "LEFT"
    elif abs_y >= abs_x and abs_y >= abs_z:
        return "UP" if peak_gyro_y < 0 else "DOWN"
    
    return None


def update_gesture_window(gx, gy, gz):
    """Update rolling window and detect gesture completion. Returns gesture label or None."""
    global gesture_in_progress, peak_gyro_x, peak_gyro_y, peak_gyro_z, gesture_sample_count
    
    gyro_window.append((gx, gy, gz))
    gyro_mag = (gx**2 + gy**2 + gz**2) ** 0.5
    
    # Motion started
    if not gesture_in_progress and gyro_mag > GYRO_MOTION_THRESHOLD:
        gesture_in_progress = True
        peak_gyro_x = gx
        peak_gyro_y = gy
        peak_gyro_z = gz
        gesture_sample_count = 0
        print("Gesture motion started")
        return None
    
    # Update peak if we're in motion
    if gesture_in_progress:
        gesture_sample_count += 1

        if abs(gx) > abs(peak_gyro_x):
            peak_gyro_x = gx
        if abs(gy) > abs(peak_gyro_y):
            peak_gyro_y = gy
        if abs(gz) > abs(peak_gyro_z):
            peak_gyro_z = gz
        
        # Motion ended (check last few samples to debounce)
        if gyro_mag < GYRO_MOTION_THRESHOLD and gesture_sample_count > 3:
            gesture_in_progress = False
            label = classify_gesture_peak()
            peak_gyro_x = peak_gyro_y = peak_gyro_z = 0
            if label:
                print(f"Detected gesture: {label}")
            else:
                print("Gesture ended but no label was assigned")
            return label
    
    return None


def process_imu(timestamp: int, sensor: Dict[str, Any]):
    global recording, buffer

    if not recording:
        return {"status": "not recording"}

    row = build_row(timestamp, sensor)

    with lock:
        buffer.append(row)

    # Classify gesture
    gesture = update_gesture_window(sensor["gyro_x"], sensor["gyro_y"], sensor["gyro_z"])

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

    try:
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
    except WebSocketDisconnect:
        print("WebSocket disconnected")

@app.get("/")
def root():
    return {"message": "IMU Data Listener is running."}