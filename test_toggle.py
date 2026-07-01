import json

import requests


BASE_URL = "http://127.0.0.1:40800"


def set_ack(enabled):
    print(f"[*] Setting ACK to {enabled}")
    requests.post(f"{BASE_URL}/api/settings", json={"ack_enabled": enabled}, timeout=3)


def send_event():
    payload = {
        "eventType": "AccessControllerEvent",
        "dateTime": "2026-06-17T14:02:04-03:00",
        "ipAddress": "192.168.1.14",
        "AccessControllerEvent": {
            "deviceName": "subdoorOne",
            "subEventType": 76,
            "serialNo": 7675,
        },
    }
    try:
        resp = requests.post(
            f"{BASE_URL}/",
            files={"event_log": (None, json.dumps(payload), "application/json")},
            timeout=3,
        )
        print(f"-> Response: {resp.status_code}")
    except Exception as e:
        print(f"-> Error: {e}")


if __name__ == "__main__":
    print("--- Test 1: ACK ON ---")
    set_ack(True)
    send_event()

    print("\n--- Test 2: ACK OFF ---")
    set_ack(False)
    send_event()

    print("\n--- Test 3: Restore ACK ON ---")
    set_ack(True)
    send_event()
