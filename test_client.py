import requests
import json
import time
import base64

SERVER_URL = "http://127.0.0.1:30000"

# Mock event data based on user request
mock_lpr_event = {
   "Picture" : {
      "CutoutPic" : {
         "Content" : "base64_placeholder", 
         "PicName" : "HOO3A88-20260114160258-plate.jpg"
      },
      "Plate" : {
         "BoundingBox" : [ 2202, 573, 2375, 623 ],
         "Channel" : 0,
         "Confidence" : 85,
         "IsExist" : True,
         "PlateColor" : "White",
         "PlateNumber" : "TEST-123",
         "PlateType" : "Unknown",
         "Region" : "BRA",
         "UploadNum" : 90
      },
      "SnapInfo" : {
         "AccurateTime" : "2026-01-14 16:02:58.157",
         "DeviceID" : "69c87cc1-testing",
         "SnapTime" : "2026-01-14 16:02:58",
      },
      "Vehicle" : {
         "VehicleColor" : "Red",
         "VehicleType" : "SaloonCar"
      }
   }
}

mock_keepalive = {
   "Active" : "keepAlive",
   "DeviceID" : "69c87cc1-testing"
}

def send_lpr_event():
    url = f"{SERVER_URL}/NotificationInfo/TollgateInfo"
    print(f"Sending LPR Event to {url}...")
    try:
        resp = requests.post(url, json=mock_lpr_event, timeout=2)
        print(f"Response: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Failed: {e}")

def send_keepalive():
    url = f"{SERVER_URL}/notification"
    print(f"Sending KeepAlive to {url}...")
    try:
        resp = requests.post(url, json=mock_keepalive, timeout=2)
        print(f"Response: {resp.status_code} {resp.text}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    print("1. Sending normal LPR event")
    send_lpr_event()
    
    print("\n2. Sending Keepalive")
    send_keepalive()
    
    print("\nCheck the Server UI to see these events.")
