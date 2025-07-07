# app.py
from flask import Flask, Response, request, abort
import cv2
import numpy as np
import time
import threading
import queue
import mysql.connector
from datetime import datetime
import os
import base64
import requests
from light_simulator import LightSimulator
from light_controller import send_light_command

# --- Configuration ---
USE_SIMULATOR = False
RTSP_URL = "rtsp://admin:Test@321@192.168.1.64/Streaming/Channels/101/"
FRAME_INTERVAL = 5
ANPR_API_URL = "https://b131-2405-201-e005-304f-30fb-eddd-b17a-b39d.ngrok-free.app/"

frame_queue = queue.Queue(maxsize=5)
unmatched_counter = {}
recent_logged_plates = {}

light = LightSimulator() if USE_SIMULATOR else None

def control_light(registered, plate):
    if USE_SIMULATOR:
        getattr(light, 'green' if registered else 'red')()
        time.sleep(2)
        light.off()
    else:
        send_light_command(plate, registered)

def mask_watermark(frame):
    frame[0:60, 0:250] = 0
    return frame

# --- MySQL Database ---
db = mysql.connector.connect(
    host="193.203.184.52",
    user="u691581411_vipras_erp",
    password="Vipras_erp@123",
    database="u691581411_vipras_erp"
)
cursor = db.cursor()

# --- Flask App ---
app = Flask(__name__)
os.makedirs("plates", exist_ok=True)

# --- Remote ANPR Helpers ---
def is_valid_api_key_remote(key):
    try:
        r = requests.get(f"{ANPR_API_URL}/validate_key", params={"api_key": key})
        return r.json().get("valid", False)
    except:
        return False

def increment_api_key_usage_remote(key):
    try:
        requests.get(f"{ANPR_API_URL}/increment_key", params={"api_key": key})
    except:
        pass

def get_plates_from_remote(frame):
    _, buffer = cv2.imencode('.jpg', frame)
    b64_frame = base64.b64encode(buffer).decode('utf-8')
    try:
        r = requests.post(f"{ANPR_API_URL}/process_frame", json={"frame": b64_frame})
        return r.json().get("plates", [])
    except:
        return []

# --- OCR Thread Worker ---
def ocr_worker():
    while True:
        frame = frame_queue.get()
        if frame is None:
            break
        try:
            plates = get_plates_from_remote(frame)
            now = datetime.now()
            for plate in plates:
                cursor.execute("SELECT plate FROM registered_vehicles WHERE plate = %s", (plate,))
                match = cursor.fetchone()
                ts = now.strftime('%Y-%m-%d %H:%M:%S')

                if match:
                    if plate in recent_logged_plates and time.time() - recent_logged_plates[plate] < 300:
                        continue
                    cursor.execute(
                        "INSERT INTO vehicle_logs (plate, timestamp, status, image_path) VALUES (%s, %s, %s, %s)",
                        (plate, ts, 'registered', '')
                    )
                    db.commit()
                    control_light(True, plate)
                    recent_logged_plates[plate] = time.time()
                    print(f"✅ {plate} allowed at {ts}")
                else:
                    unmatched_counter.setdefault(plate, 0)
                    unmatched_counter[plate] += 1

                    if unmatched_counter[plate] >= 2:
                        if plate in recent_logged_plates and time.time() - recent_logged_plates[plate] < 300:
                            continue
                        img_path = f"plates/unregistered_{plate}_{now.strftime('%Y%m%d_%H%M%S')}.jpg"
                        cursor.execute(
                            "INSERT INTO vehicle_logs (plate, timestamp, status, image_path) VALUES (%s, %s, %s, %s)",
                            (plate, ts, 'unregistered', img_path)
                        )
                        db.commit()
                        cv2.imwrite(img_path, frame)
                        control_light(False, plate)
                        unmatched_counter.pop(plate, None)
                        recent_logged_plates[plate] = time.time()
                        print(f"🚫 Logged unregistered: {plate}")
        except Exception as e:
            print("❌ OCR worker error:", e)
        frame_queue.task_done()

@app.route('/')
def index():
    return "<h1>ANPR System</h1><p>Use /video_feed?api_key=42afd4b05354429cb4e57219eea353ce to stream video.</p>"

@app.route('/video_feed')
def video_feed():
    api_key = request.args.get('api_key')
    if not api_key or not is_valid_api_key_remote(api_key):
        abort(401, description="Invalid or missing API key")

    def stream():
        cap = cv2.VideoCapture(RTSP_URL)
        if not cap.isOpened():
            while True:
                blank = np.zeros((480, 640, 3), np.uint8)
                cv2.putText(blank, "Stream Unavailable", (100, 240), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                _, buffer = cv2.imencode('.jpg', blank)
                yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'

        frame_count = 0
        while True:
            ret, frame = cap.read()
            if not ret:
                continue

            frame = mask_watermark(frame)

            if frame_count % FRAME_INTERVAL == 0:
                try:
                    frame_queue.put_nowait(frame.copy())
                except queue.Full:
                    pass

            _, buffer = cv2.imencode('.jpg', frame)
            yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
            frame_count += 1

    increment_api_key_usage_remote(api_key)
    return Response(stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

# --- Start OCR Thread and Server ---
if __name__ == '__main__':
    threading.Thread(target=ocr_worker, daemon=True).start()
    app.run(host='0.0.0.0', port=5000, debug=False)
