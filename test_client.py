import io
import json

import requests


SERVER_URL = "http://127.0.0.1:40800"


mock_access_event = {
    "ipAddress": "192.168.1.14",
    "portNo": 40800,
    "protocol": "HTTP",
    "macAddress": "e0:ca:3c:e8:e2:ab",
    "channelID": 1,
    "dateTime": "2026-06-17T14:02:04-03:00",
    "activePostCount": 1,
    "eventType": "AccessControllerEvent",
    "eventState": "active",
    "eventDescription": "Access Controller Event",
    "AccessControllerEvent": {
        "deviceName": "subdoorOne",
        "majorEventType": 5,
        "subEventType": 76,
        "cardReaderKind": 1,
        "cardReaderNo": 1,
        "verifyNo": 164,
        "serialNo": 7675,
        "currentVerifyMode": "cardOrfaceOrPw",
        "frontSerialNo": 7674,
        "attendanceStatus": "undefined",
        "label": "",
        "statusValue": 0,
        "mask": "unknown",
        "picturesNumber": 1,
        "purePwdVerifyEnable": True,
        "FaceRect": {
            "height": 0.324,
            "width": 0.183,
            "x": 0.426,
            "y": 0.198,
        },
    },
}


def send_access_event():
    files = {
        "event_log": (None, json.dumps(mock_access_event), "application/json"),
        "facePic": ("face.jpg", io.BytesIO(b"\xff\xd8\xff\xe0mock-jpeg\xff\xd9"), "image/jpeg"),
    }
    print(f"Sending Hikvision facial event to {SERVER_URL}/ ...")
    try:
        resp = requests.post(f"{SERVER_URL}/", files=files, timeout=3)
        print(f"Response: {resp.status_code} {resp.text!r}")
    except Exception as e:
        print(f"Failed: {e}")


def send_heartbeat():
    print(f"Sending heartbeat to {SERVER_URL}/ ...")
    try:
        resp = requests.post(f"{SERVER_URL}/", json={"eventType": "heartBeat"}, timeout=3)
        print(f"Response: {resp.status_code} {resp.text!r}")
    except Exception as e:
        print(f"Failed: {e}")


if __name__ == "__main__":
    print("1. Sending facial event")
    send_access_event()

    print("\n2. Sending heartbeat")
    send_heartbeat()

    print("\nCheck the server UI to see the event.")
