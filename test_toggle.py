import requests
import json

BASE_URL = "http://127.0.0.1:30000"

def set_ack(enabled):
    print(f"[*] Setting ACK to {enabled}")
    requests.post(f"{BASE_URL}/api/settings", json={"ack_enabled": enabled})

def send_event():
    url = f"{BASE_URL}/NotificationInfo/TollgateInfo"
    try:
        resp = requests.post(url, json={"test": "data"}, timeout=1)
        print(f"-> Response: {resp.status_code}")
    except Exception as e:
        print(f"-> Error: {e}")

if __name__ == "__main__":
    print("--- Test 1: ACK ON (Default) ---")
    set_ack(True)
    send_event()
    
    print("\n--- Test 2: ACK OFF ---")
    set_ack(False)
    send_event()

    print("\n--- Test 3: Restore ACK ON ---")
    set_ack(True)
    send_event()
