import csv
from fastapi import FastAPI, Request
from pydantic import BaseModel
from typing import List, Dict, Any
from datetime import datetime
import threading

app = FastAPI()

# State
recording = False
current_label = None
session_id = 0
buffer = []
lock = threading.Lock()

# Data
class Sensor(BaseModel):
    accel_x: float
    accel_y: float
    accel_z: float
    gyro_x: float
    gyro_y: float
    gyro_z: float
    temp: float

class IMUData(BaseModel):
    timestamp: int
    device_id: str
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


# receive data
@app.post("/data")
async def ingest(data: IMUData):
    global recording, buffer
    if not recording:
        return {"status": "not recording"}
    
    row = [
        data.device_id,
        datetime.now().isoformat(),
        data.timestamp,

        data.sensor.accel_x,
        data.sensor.accel_y,
        data.sensor.accel_z,
        data.sensor.gyro_x,
        data.sensor.gyro_y,
        data.sensor.gyro_z,
        data.sensor.temp,
        abs(data.sensor.accel_x) + abs(data.sensor.accel_y) + abs(data.sensor.accel_z)  + abs(data.sensor.gyro_x) + abs(data.sensor.gyro_y) + abs(data.sensor.gyro_z)
    ]

    with lock:
        buffer.append(row)

    return {"status": "data received"}

# save + stop
@app.post("/stop")
def stop_session():
    global recording, buffer, current_label, session_id

    if not recording:
        return {"status": "not recording"}
    
    filename = f"{current_label}_{session_id}.csv"

    headers = [
        "device_id",
        "timestamp",
        "received_at",
        "accel_x",
        "accel_y",
        "accel_z",
        "gyro_x",
        "gyro_y",
        "gyro_z",
        "temp",
        "motion_magnitude"
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