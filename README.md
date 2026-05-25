# Motion-Mouse

Motion-Mouse is a data collection project for IMU-driven gesture recognition.  
It captures accelerometer and gyroscope samples from an ESP32 + MPU6050 setup, stores labeled flick sessions as CSV files, and prepares data for downstream analysis/classification.

The long-term goal is:
1. classify each motion (for example: left/right/up/down flick),
2. map each classified motion to a mouse action.

---

## Project Purpose

This repository focuses on the **data pipeline** stage:
- stream IMU samples from hardware,
- label recording sessions by gesture type,
- persist clean datasets for training and experimentation.

Machine learning classification is not yet implemented in this repository, but the data format and workflow are designed to support it.

---

## Repository Structure

- `/esp32_data.ino`  
  ESP32 firmware that reads MPU6050 sensor data and sends JSON payloads to the listener API.

- `/listener.py`  
  FastAPI server that starts/stops labeled recording sessions and writes captured samples to CSV.

- `/flicks/`  
  Example recorded datasets grouped by flick class:
  - `left_flick`
  - `right_flick`
  - `up_flick`
  - `down_flick`

---

## High-Level Architecture

1. **Label selection**  
   A gesture label is entered over serial on boot (for example `left_flick`).

2. **Session control**  
   ESP32 calls:
   - `POST /start?label=<label>` to begin a capture session
   - `POST /save` (or `/stop`) to persist data and end session

3. **Sample streaming**  
   While recording is active, ESP32 sends `POST /data` payloads on a fixed interval.

4. **Dataset creation**  
   The server buffers incoming samples and writes `<label>_<session_id>.csv` when stopped.

---

## Data Schema

### Incoming JSON (`POST /data`)
- `device_id`
- `timestamp` (device-side timestamp from `millis()`)
- `sensor`
  - `accel_x`, `accel_y`, `accel_z`
  - `gyro_x`, `gyro_y`, `gyro_z`
  - `temp`

### Output CSV columns
- `device_id`
- `timestamp`
- `received_at`
- `accel_x`
- `accel_y`
- `accel_z`
- `gyro_x`
- `gyro_y`
- `gyro_z`
- `temp`

---

## Local Setup

### 1) Run the FastAPI listener

Install dependencies:

```bash
pip install fastapi uvicorn pydantic
```

Start the server:

```bash
uvicorn listener:app --host 0.0.0.0 --port 8000
```

### 2) Configure firmware

In `esp32_data.ino`, update:
- `ssid`
- `serverURL` (must point to the machine running FastAPI)

Then flash the sketch to your ESP32.

---

## Data Collection Workflow

1. Open serial monitor at `115200`.
2. Enter label name (example: `left_flick`).
3. Press the hardware button to toggle recording.
4. Perform repeated flick motions.
5. Press button again to stop and force-save.
6. Move resulting CSV files into class folders (for example under `flicks/left_flick`).

Repeat across classes and users/sessions to build a balanced dataset.

---

## Extending Toward a Motion-to-Mouse Classifier

Next steps this repo enables:
- feature extraction from accel/gyro time-series,
- training a gesture classifier (classical ML or deep learning),
- real-time inference on incoming IMU windows,
- mapping predicted gestures to mouse commands (move, click, scroll, etc.).

---

## Current Status

- ✅ End-to-end IMU data capture pipeline exists
- ✅ Labeled CSV generation exists
- ✅ Example flick datasets are included
- ⏳ Classification model and mouse action runtime mapping are future work
