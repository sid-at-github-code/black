/*
  LED + SERVO HTTP FAST API CONNECTION
*/

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266mDNS.h>
#include <ArduinoJson.h>
#include <Servo.h>

// ── CONFIG ──
const char* WIFI_SSID  = "Airtel_Jarvis_0206";
const char* WIFI_PASS  = "diodeop0206";
const int   SERVER_PORT = 5000;

const int LED_PIN    = 2;      // GPIO2 (D4) — onboard LED, active LOW
const int SERVO_PIN  = 5;      // GPIO5 (D1) — servo signal
const int POLL_MS    = 500;

WiFiClient wifiClient;
String serverIP = "";
Servo servo1;

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);

  servo1.attach(SERVO_PIN);
  servo1.write(90);  // rest position

  WiFi.begin(WIFI_SSID, WIFI_PASS);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected! IP: " + WiFi.localIP().toString());

  if (!MDNS.begin("pothole_esp")) {
    Serial.println("mDNS init failed");
  }

  resolveServer();
}

void resolveServer() {
  Serial.println("Searching for server via mDNS...");

  for (int attempt = 0; attempt < 10; attempt++) {
    int n = MDNS.queryService("http", "tcp");
    if (n > 0) {
      for (int i = 0; i < n; i++) {
        String name = MDNS.hostname(i);
        Serial.println("Found: " + name + " @ " + MDNS.IP(i).toString());
        if (name.startsWith("carserver")) {
          serverIP = MDNS.IP(i).toString();
          Serial.println("Server resolved: " + serverIP);
          return;
        }
      }
    }
    delay(1000);
  }
  Serial.println("mDNS resolve failed — will retry in loop");
}

void doAlert() {
  // LED blink
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, LOW);   // ON (active low)
    delay(150);
    digitalWrite(LED_PIN, HIGH);  // OFF
    delay(100);
  }

  // Servo sequence: 45° (160ms) → wait 2s → 135° (160ms) → back to 90°
  servo1.write(45);
  delay(160);

  servo1.write(90);
  delay(2000);

  servo1.write(135);
  delay(160);

  servo1.write(90);  // back to rest
}

void loop() {
  MDNS.update();

  if (WiFi.status() != WL_CONNECTED) {
    delay(1000);
    return;
  }

  if (serverIP == "") {
    resolveServer();
    if (serverIP == "") {
      delay(2000);
      return;
    }
  }

  HTTPClient http;
  String url = "http://" + serverIP + ":" + String(SERVER_PORT) + "/status";

  http.begin(wifiClient, url);
  int code = http.GET();

  if (code == 200) {
    String body = http.getString();
    StaticJsonDocument<128> doc;
    if (deserializeJson(doc, body) == DeserializationError::Ok) {
      bool blink = doc["blink"] | false;
      int count  = doc["count"] | 0;
      if (blink) {
        Serial.println("POTHOLE! Count: " + String(count));
        doAlert();
      }
    }
  } else if (code < 0) {
    Serial.println("Connection failed, re-resolving...");
    serverIP = "";
  }

  http.end();
  delay(POLL_MS);
}