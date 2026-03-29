/*
  pothole_esp.ino
  ===============
  ESP8266 HTTP polling via mDNS service discovery.
  Finds carserver._http._tcp.local, polls GET /status every 500ms.
  If blink=true → flash LED + buzzer.
*/

#include <ESP8266WiFi.h>
#include <ESP8266HTTPClient.h>
#include <ESP8266mDNS.h>
#include <ArduinoJson.h>

// ── CONFIG ──
const char* WIFI_SSID  = "Airtel_Jarvis_0206";
const char* WIFI_PASS  = "diodeop0206";
const int   SERVER_PORT = 8000;

const int LED_PIN    = 2;      // GPIO2 (D4) — onboard LED, active LOW
const int BUZZER_PIN = 14;     // GPIO14 (D5) — buzzer pin
const int POLL_MS    = 500;

WiFiClient wifiClient;
String serverIP = "";

void setup() {
  Serial.begin(115200);
  pinMode(LED_PIN, OUTPUT);
  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  digitalWrite(BUZZER_PIN, LOW);

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

void doBlink() {
  for (int i = 0; i < 3; i++) {
    digitalWrite(LED_PIN, LOW);
    digitalWrite(BUZZER_PIN, HIGH);
    delay(150);
    digitalWrite(LED_PIN, HIGH);
    digitalWrite(BUZZER_PIN, LOW);
    delay(100);
  }
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
        doBlink();
      }
    }
  } else if (code < 0) {
    Serial.println("Connection failed, re-resolving...");
    serverIP = "";
  }

  http.end();
  delay(POLL_MS);
}