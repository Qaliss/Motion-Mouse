#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>

const char* ssid = "OpenWrt";

String currentLabel = "";

const String serverURL = "http://192.168.1.244:8000/";


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

  HTTPClient http;
  String startUrl = serverURL + "start?label=" + currentLabel;
  Serial.print("hitting URL: ");
  Serial.println(startUrl);
  http.begin(startUrl);
  http.POST("");
  http.end();
  Serial.println("Session started on server");
}


void loop() {

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

void toggleRecording() {
  isRecording = !isRecording;
  
  if (isRecording) {
    Serial.println("=== RECORDING STARTED ===");
    digitalWrite(LED_PIN, HIGH);

    HTTPClient http;
    String startURL = "http://192.168.1.244:8000/start?label=" + currentLabel;
    http.begin(startURL);
    http.POST("");
    http.end();

  } else {
    Serial.println("=== RECORDING STOPPED ===");
    digitalWrite(LED_PIN, LOW);
    forceSave();
  }
}

void sendIMUData() {
  sensors_event_t accel, gyro, temp;
  
  mpu.getEvent(&accel, &gyro, &temp);

  StaticJsonDocument<512> doc;

  doc["device_id"] = deviceID;
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

  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;

    http.begin(serverURL + "data");
    http.addHeader("Content-Type", "application/json");

    int httpResponseCode = http.POST(jsonString);
    Serial.print("Attempting to connect to: ");
  Serial.println(serverURL);

    if (httpResponseCode > 0) {
      Serial.printf("Data sent successfully. Response %d\n", httpResponseCode);
    } else {
      Serial.printf("Error sending data %d\n", httpResponseCode);
    }

    http.end();
  } else {
    Serial.println("Wifi not connected");
  }
}

void forceSave() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    String saveURL = serverURL + "save";
    
    http.begin(saveURL);
    int httpResponseCode = http.POST("");
    
    if (httpResponseCode > 0) {
      Serial.println("Forced save to CSV successful");
    } else {
      Serial.println("Failed to force save");
    }
    
    http.end();
  }
}

