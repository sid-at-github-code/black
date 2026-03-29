"""
pothole_server_cam.py
=====================
FastAPI HTTP server + Pothole detection (WEBCAM only).
mDNS hostname: carserver.local:8000

Install deps:
    pip install fastapi uvicorn opencv-python numpy zeroconf

Run:
    python pothole_server_cam.py
"""

import asyncio
import cv2
import math
import numpy as np
import os
import threading
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from zeroconf import ServiceInfo, Zeroconf
import socket


# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
CAM_INDEX      = 0             # change if you have multiple cameras
CAM_WIDTH      = 1280
CAM_HEIGHT     = 720

MDNS_HOSTNAME  = "carserver"
SERVER_HOST    = "0.0.0.0"
SERVER_PORT    = 8000

# ─────────────────────────────────────────────
#  ML PARAMETERS
# ─────────────────────────────────────────────
MIN_AREA          = 6000
MAX_AREA          = 40000
DARK_MEAN_THRESH  = 200
ASPECT_RATIO_MIN  = 1.2
ASPECT_RATIO_MAX  = 3.2
ROI_Y_START_FRAC  = 0.35
CONFIRM_FRAMES    = 3
MAX_LOST_FRAMES   = 5
MAX_MATCH_DIST    = 60


# ─────────────────────────────────────────────
#  GLOBAL STATE
# ─────────────────────────────────────────────
blink_flag = False
blink_lock = threading.Lock()

ml_thread: threading.Thread | None = None
ml_running = False
unique_pothole_count = 0

_zc_instance: Zeroconf | None = None
_zc_info: ServiceInfo | None  = None


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def centroid_from_bbox(bbox):
    x, y, w, h = bbox
    return (int(x + w / 2), int(y + h / 2))


def euclid(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def trigger_blink():
    global blink_flag
    with blink_lock:
        blink_flag = True


# ─────────────────────────────────────────────
#  ML LOOP  (webcam only)
# ─────────────────────────────────────────────
def run_ml_pipeline():
    global ml_running, unique_pothole_count

    print("\n[ML] ─────────────────────────────────────────")
    print(f"[ML] Opening WEBCAM index={CAM_INDEX} via DirectShow...")
    cap = cv2.VideoCapture(CAM_INDEX, cv2.CAP_DSHOW)

    if not cap.isOpened():
        print(f"[ML] ❌ Cannot open webcam index={CAM_INDEX}")
        ml_running = False
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  CAM_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)

    W   = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    H   = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

    print(f"[ML] Resolution : {W}x{H}")
    print(f"[ML] FPS        : {fps}")
    print("[ML] Pipeline running… Press Q in the OpenCV window to stop.\n")

    kernel  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    bg_sub  = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=50, detectShadows=False)
    delay   = max(1, int(1000 / fps))

    frame_idx     = 0
    next_track_id = 1
    tracks        = {}

    while ml_running:
        ret, frame = cap.read()
        if not ret:
            print("[ML] ⚠️  Frame grab failed — retrying...")
            time.sleep(0.05)
            continue

        frame_idx += 1
        y_start = int(H * ROI_Y_START_FRAC)
        roi     = frame[y_start:H, 0:W]

        # ── Preprocessing ──
        gray      = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.GaussianBlur(gray, (7, 7), 0)
        clahe     = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_eq   = clahe.apply(gray_blur)

        # ── Background subtraction ──
        fg = bg_sub.apply(gray_eq)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN,  kernel, iterations=1)
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=2)

        # ── Edge + dark detection ──
        edges = cv2.Canny(gray_eq, 60, 140)
        _, dark = cv2.threshold(gray_eq, DARK_MEAN_THRESH, 255, cv2.THRESH_BINARY_INV)

        combined = cv2.bitwise_and(fg, dark)
        combined = cv2.bitwise_or(combined, edges)
        combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)
        combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN,  kernel, iterations=1)

        # ── Contours ──
        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < MIN_AREA or area > MAX_AREA:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            ar = w / float(h + 1e-6)
            if not (ASPECT_RATIO_MIN <= ar <= ASPECT_RATIO_MAX):
                continue

            solidity = float(area) / (w * h + 1e-6)
            if solidity < 0.2:
                continue

            roi_patch = gray_eq[y:y + h, x:x + w]
            mean_int  = float(np.mean(roi_patch)) if roi_patch.size else 255
            if mean_int > DARK_MEAN_THRESH + 20:
                continue

            detections.append((x, y, w, h, area, mean_int))

        # ── Tracking ──
        unmatched_dets = set(range(len(detections)))
        matched_tracks = set()
        det_centroids  = [centroid_from_bbox((d[0], d[1], d[2], d[3])) for d in detections]
        track_items    = list(tracks.items())

        for di, det_c in enumerate(det_centroids):
            best_tid, best_dist = None, float('inf')
            for tid, tdata in track_items:
                if tid in matched_tracks:
                    continue
                dist = euclid(det_c, tdata['centroid'])
                if dist < best_dist:
                    best_dist, best_tid = dist, tid

            if best_tid is not None and best_dist <= MAX_MATCH_DIST:
                td = tracks[best_tid]
                td['bbox']        = (detections[di][0], detections[di][1], detections[di][2], detections[di][3])
                td['centroid']    = det_centroids[di]
                td['consecutive'] = td['consecutive'] + 1 if frame_idx - td['last_seen'] == 1 else 1
                td['last_seen']   = frame_idx
                matched_tracks.add(best_tid)
                unmatched_dets.discard(di)

        for di in list(unmatched_dets):
            x, y, w, h, area, mean_int = detections[di]
            cid = next_track_id
            next_track_id += 1
            tracks[cid] = {
                'bbox':        (x, y, w, h),
                'centroid':    det_centroids[di],
                'first_seen':  frame_idx,
                'last_seen':   frame_idx,
                'consecutive': 1,
                'counted':     False,
            }

        # ── Confirm & TRIGGER ──
        for tid, tdata in list(tracks.items()):
            if (not tdata['counted']) and (tdata['consecutive'] >= CONFIRM_FRAMES):
                tdata['counted']      = True
                unique_pothole_count += 1
                print(f"\n[ML] 🚨 POTHOLE CONFIRMED  id={tid}  frame={frame_idx}  total={unique_pothole_count}")
                trigger_blink()

        # ── Stale track cleanup ──
        for tid in [t for t, td in list(tracks.items()) if frame_idx - td['last_seen'] > MAX_LOST_FRAMES]:
            del tracks[tid]

        # ── Draw ──
        for (x, y, w, h, *_) in detections:
            cv2.rectangle(frame, (x, y + y_start), (x + w, y + h + y_start), (0, 0, 255), 2)

        for tid, tdata in tracks.items():
            x, y, w, h = tdata['bbox']
            tl    = (int(x), int(y + y_start))
            br    = (int(x + w), int(y + h + y_start))
            color = (0, 255, 0) if tdata['counted'] else (255, 165, 0)
            cv2.rectangle(frame, tl, br, color, 1)
            cv2.putText(frame, f"id{tid} c{tdata['consecutive']}",
                        (tl[0], max(tl[1] - 8, 0)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

        # HUD
        cv2.putText(frame, f"Potholes: {unique_pothole_count}",
                    (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

        cv2.imshow('Pothole Detector [CAM] — Q to quit', frame)
        if cv2.waitKey(delay) & 0xFF in (ord('q'), 27):
            print("[ML] 🛑 User pressed Q — stopping.")
            break

    cap.release()
    cv2.destroyAllWindows()
    ml_running = False
    print(f"\n[ML] ✅ Done. Frames: {frame_idx}  Potholes: {unique_pothole_count}")


# ─────────────────────────────────────────────
#  mDNS
# ─────────────────────────────────────────────
def start_mdns():
    global _zc_instance, _zc_info

    local_ip = socket.gethostbyname(socket.gethostname())
    print(f"\n[mDNS] Local IP   : {local_ip}")
    print(f"[mDNS] Advertising: {MDNS_HOSTNAME}.local:{SERVER_PORT}")

    info = ServiceInfo(
        type_="_http._tcp.local.",
        name=f"{MDNS_HOSTNAME}._http._tcp.local.",
        addresses=[socket.inet_aton(local_ip)],
        port=SERVER_PORT,
        properties={"path": "/status"},
        server=f"{MDNS_HOSTNAME}.local.",
    )

    def _run_zeroconf():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        zc = Zeroconf()
        zc.register_service(info)
        print(f"[mDNS] ✅ Registered — ESP8266 → http://{MDNS_HOSTNAME}.local:{SERVER_PORT}/status\n")
        global _zc_instance, _zc_info
        _zc_instance = zc
        _zc_info     = info
        try:
            loop.run_forever()
        finally:
            zc.unregister_service(info)
            zc.close()
            loop.close()

    t = threading.Thread(target=_run_zeroconf, daemon=True, name="zeroconf")
    t.start()
    time.sleep(0.8)


# ─────────────────────────────────────────────
#  FASTAPI
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global ml_thread, ml_running

    start_mdns()

    ml_running = True
    ml_thread  = threading.Thread(target=run_ml_pipeline, daemon=True, name="ml-pipeline")
    ml_thread.start()
    print("[Server] 🚀 ML pipeline thread started.")
    print(f"[Server] 🌐 HTTP: http://0.0.0.0:{SERVER_PORT}/status\n")

    yield

    print("\n[Server] ⏹  Shutting down…")
    ml_running = False
    if ml_thread:
        ml_thread.join(timeout=3)
    print("[Server] 👋 Done.")


app = FastAPI(title="Pothole IoT Server — CAM", lifespan=lifespan)


@app.get("/status")
def get_status():
    """ESP polls this. Returns blink=true once, then auto-resets."""
    global blink_flag
    with blink_lock:
        val = blink_flag
        blink_flag = False
    return {"blink": val, "count": unique_pothole_count}


@app.get("/")
async def root():
    return {
        "mode": "webcam",
        "cam_index": CAM_INDEX,
        "endpoint": f"http://{MDNS_HOSTNAME}.local:{SERVER_PORT}/status",
        "ml_running": ml_running,
        "potholes": unique_pothole_count,
    }


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 55)
    print("  🛣️  Pothole IoT Server  [WEBCAM MODE — HTTP]")
    print(f"  CAM  : index {CAM_INDEX}  ({CAM_WIDTH}x{CAM_HEIGHT})")
    print(f"  mDNS : {MDNS_HOSTNAME}.local:{SERVER_PORT}")
    print(f"  Poll : http://{MDNS_HOSTNAME}.local:{SERVER_PORT}/status")
    print("=" * 55)

    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="warning")