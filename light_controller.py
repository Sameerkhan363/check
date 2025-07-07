import requests

ESP32_IP = "http://192.168.58.52"  # Replace with your ESP32 IP

def send_light_command(plate, registered):
    try:
        url = f"{ESP32_IP}/status?plate={plate}&registered={str(registered).lower()}"
        response = requests.get(url, timeout=3)
        print("ESP32 Response:", response.text)
    except Exception as e:
        print("❌ ESP32 communication failed:", e)
