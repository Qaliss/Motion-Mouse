#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <WebSocketsClient.h>

const char* ssid = "OpenWrt";

String currentLabel = "";
WebSocketsClient webSocket;
bool pendingSessionStart = false;


Adafruit_MPU6050 mpu;


const int BUTTON_PIN = 0;
const int LED_PIN = 2;


bool isRecording = false;
bool lastButtonState = HIGH;
bool currentButtonState = HIGH;
unsigned long lastDebounceTime = 0;
const unsigned long debounceDelay = 50;

unsigned long lastSend = 0;
const int sendInterval = 50;


const String deviceID = "ESP32_01";

void setup() {
  Serial.begin(115200);

  pinMode(BUTTON_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, LOW);

  Wire.begin();

  Serial.println("Intitializing IMU sensor...");

  if (!mpu.begin()) {
    Serial.println("Failed to find IMU");
    while (1) {
      digitalWrite(LED_PIN, !digitalRead(LED_PIN));
      delay(100);
    }
  }

  Serial.println("IMU Sensor initialized successfully");


  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);


  WiFi.begin(ssid);
  Serial.print("Connecting to WiFi");

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }


  Serial.println();
  Serial.println("WiFi connected");
  Serial.print("IP Address: ");
  Serial.println(WiFi.localIP());
  Serial.println("Ready to send IMU data");

  digitalWrite(LED_PIN, LOW);

  Serial.println("Enter punch label (e.g. left_jab, right_hook):");
  while (currentLabel == "") {
    if (Serial.available()) {
      currentLabel = Serial.readStringUntil('\n');
      currentLabel.trim();
      currentLabel.replace("\r", "");
      currentLabel.replace(" ", "_");
    }
  }

  Serial.print("Label set to: ");
  Serial.println(currentLabel);

  pendingSessionStart = true;

  webSocket.begin("192.168.1.244", 8000, "/ws");
  webSocket.onEvent(webSocketEvent);
  webSocket.setReconnectInterval(5000);

}


void loop() {
  webSocket.loop();
  checkButton();

    // Only send data if recording
    if (isRecording && (millis() - lastSend >= sendInterval)) {
      sendIMUData();
      lastSend = millis();
    }

    // Blink LED when recording
    if (isRecording) {
      static unsigned long lastBlink = 0;
      if (millis() - lastBlink >= 500) {
        digitalWrite(LED_PIN, !digitalRead(LED_PIN));
        lastBlink = millis();
      }
    }
  }

void checkButton() {
  int reading = digitalRead(BUTTON_PIN);

  // Check if button state changed
  if (reading != lastButtonState) {
    lastDebounceTime = millis();
  }

  // If enough time has passed, consider it a valid state change
  if ((millis() - lastDebounceTime) > debounceDelay) {
    if (reading != currentButtonState) {
      currentButtonState = reading;

      // Button pressed (LOW because of INPUT_PULLUP)
      if (currentButtonState == LOW) {
        toggleRecording();
      }
    }
  }

  lastButtonState = reading;
}

void webSocketEvent(
  WStype_t type,
  uint8_t * payload,
  size_t length
) {
  switch(type) {
    case WStype_CONNECTED:
      Serial.println("WEBSOCKET CONNECTED");
      if (pendingSessionStart) {
        sendControlMessage("start");
        Serial.println("Session started on server");
        pendingSessionStart = false;
      }
      break;
    case WStype_DISCONNECTED:
      Serial.println("WEBSOCKET DISCONNECTED");
      break;
    case WStype_TEXT:
      Serial.printf("Received %s\n", payload);
      break;
    case WStype_ERROR:
      Serial.println("WEBSOCKET ERROR");
      break;
  }
}

void toggleRecording() {
  isRecording = !isRecording;
  
  if (isRecording) {
    Serial.println("=== RECORDING STARTED ===");
    digitalWrite(LED_PIN, HIGH);

    sendControlMessage("start");

  } else {
    Serial.println("=== RECORDING STOPPED ===");
    digitalWrite(LED_PIN, LOW);
    sendControlMessage("stop");
  }
}

void sendIMUData() {
  sensors_event_t accel, gyro, temp;
  
  mpu.getEvent(&accel, &gyro, &temp);

  StaticJsonDocument<256> doc;

  doc["device_id"] = deviceID;
  doc["type"] = "imu";
  doc["timestamp"] = millis();

  JsonObject sensor = doc["sensor"].to<JsonObject>();

  sensor["accel_x"] = accel.acceleration.x;
  sensor["accel_y"] = accel.acceleration.y;
  sensor["accel_z"] = accel.acceleration.z;

  sensor["gyro_x"] = gyro.gyro.x;
  sensor["gyro_y"] = gyro.gyro.y;
  sensor["gyro_z"] = gyro.gyro.z;

  sensor["temp"] = temp.temperature;


  String jsonString;
  serializeJson(doc, jsonString);
  
  if (webSocket.isConnected()) {
    webSocket.sendTXT(jsonString);
  }

}

void sendControlMessage(const char* action) {
  StaticJsonDocument<128> doc;
  doc["type"] = "control";
  doc["action"] = action;
  doc["label"] = currentLabel;

  String msg;
  serializeJson(doc, msg);

  if (webSocket.isConnected()) {
    webSocket.sendTXT(msg);
  }
}

void forceSave() {
  sendControlMessage("save");
}
