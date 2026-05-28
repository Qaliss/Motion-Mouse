import csv
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime
import threading
from collections import deque
import math
import time

app = FastAPI()

# State
recording = False
current_label = None
session_id = 0
buffer = []
lock = threading.Lock()

x_window = deque(maxlen = 6)

last_gesture_time = 0
COOLDOWN = 0.1

ACCEL_THRESHOLD = 10

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

# start recording
@app.post("/start")
def start_session(label: str):
    global recording, current_label, session_id, buffer

    if recording:
        return {"status": "already recording"}
    
    current_label = label
    recording = True
    buffer = []
    session_id += 1

    return {
        "status": "started",
        "label": label,
        "session_id": session_id
    }


def classify_flick():

    global x_window

    values = list(x_window)

    if len(values) < 6:
        return None
    
    max_val = max(values)
    min_val = min(values)

    max_index = values.index(max_val)
    min_index = values.index(min_val)

    if max_val > 4 and min_val < -4:
        if min_index < max_index:
            return "LEFT"
        
        if max_index < min_index:
            return "RIGHT"
        
    return None

# receive data
@app.post("/data")
async def ingest(data: IMUData):
    global recording, buffer
    if not recording:
        return {"status": "not recording"}
    
    row = [
        datetime.now().isoformat(),
        data.timestamp,

        data.sensor.accel_x,
        data.sensor.accel_y,
        data.sensor.accel_z,
        data.sensor.gyro_x,
        data.sensor.gyro_y,
        data.sensor.gyro_z,
        # Motion magnitude total, normalizing 
        (data.sensor.accel_x**2 + data.sensor.accel_y**2 + data.sensor.accel_z**2)**0.5,
        (data.sensor.gyro_x**2 + data.sensor.gyro_y**2 + data.sensor.gyro_z**2)**0.5
    ]

    with lock:
        buffer.append(row)

    ax = data.sensor.accel_x
    ay = data.sensor.accel_y
    az = data.sensor.accel_z

    x_window.append(ax)

    accel_mag = (ax**2 + ay**2 + az**2)**0.5

    global last_gesture_time

    current_time = time.time()

    if (
        accel_mag > ACCEL_THRESHOLD and current_time - last_gesture_time > COOLDOWN
    ):
        gesture = classify_flick()

        if gesture:
            print(f"Detected gesture: {gesture}")
            last_gesture_time = current_time

    return {"status": "data received"}



# save + stop
@app.post("/stop")
def stop_session():
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

    return {
        "status": "saved",
        "file": filename
    }

@app.post("/save")
def save():
    return stop_session()

@app.get("/")
def root():
    return {"message": "IMU Data Listener is running."}