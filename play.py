import cv2
import numpy as np
import math

VIDEO_IN  = "pothole_road_sample1.mp4"

# TUNABLE PARAMETERS (start with these; tweak if many false+ or misses)
MIN_AREA        = 6000
MAX_AREA        = 40000
DARK_MEAN_THRESH= 200
ASPECT_RATIO_MIN= 1.2
ASPECT_RATIO_MAX= 3.2
ROI_Y_START_FRAC = 0.35

CONFIRM_FRAMES   = 3   
MAX_LOST_FRAMES  = 5    
MAX_MATCH_DIST   = 60   

# Background subtractor helps isolate transient road defects
bg_sub = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=50, detectShadows=False)

cap = cv2.VideoCapture(VIDEO_IN)
if not cap.isOpened():
    raise SystemExit("Cannot open video file: " + VIDEO_IN)

use_weight_file=("cotom_trained.pt")

W  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7,7))

print("Processing live... ")
fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
speed = 0.8
delay = int((1000 / fps)*speed)

frame_idx = 0

# TRACKING state
next_track_id = 1
tracks = {}  # { 'bbox':(x,y,w,h), 'centroid':(cx,cy), 'first_seen':frame_idx, 'last_seen':frame_idx, 'consecutive':n, 'counted':bool }
unique_pothole_count = 0

def centroid_from_bbox(bbox):
    x, y, w, h = bbox
    return (int(x + w/2), int(y + h/2))

def euclid(a, b):
    return math.hypot(a[0]-b[0], a[1]-b[1])

while True:
    ret, frame = cap.read()
    if not ret:
        break
    frame_idx += 1

    # 1) ROI crop
    y_start = int(H * ROI_Y_START_FRAC)
    roi = frame[y_start:H, 0:W]

    # 2) Preprocess
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.GaussianBlur(gray, (7,7), 0)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray_eq = clahe.apply(gray_blur)

    # 3) Background subtraction
    fg = bg_sub.apply(gray_eq)
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel, iterations=1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 4) Edge + dark region detection combined
    edges = cv2.Canny(gray_eq, 60, 140)
    _, dark = cv2.threshold(gray_eq, DARK_MEAN_THRESH, 255, cv2.THRESH_BINARY_INV)

    combined = cv2.bitwise_and(fg, dark)
    combined = cv2.bitwise_or(combined, edges)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)
    combined = cv2.morphologyEx(combined, cv2.MORPH_OPEN, kernel, iterations=1)

    # 5) Find contours and filter
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
        bbox_area = w * h
        solidity = float(area) / (bbox_area + 1e-6)
        if solidity < 0.2:
            continue
        roi_patch = gray_eq[y:y+h, x:x+w]
        mean_int = float(np.mean(roi_patch)) if roi_patch.size else 255
        if mean_int > DARK_MEAN_THRESH + 20:
            continue
        detections.append((x, y, w, h, area, mean_int))

    # TRACKING: match detections -> existing tracks (centroid distance)
    unmatched_dets = set(range(len(detections)))
    matched_tracks = set()
    det_centroids = [centroid_from_bbox((d[0], d[1], d[2], d[3])) for d in detections]

    # Build list of track centroids (in ROI coords)
    track_items = list(tracks.items())  # (track_id, data)
    # For each detection, try to find the closest track
    for di, det_c in enumerate(det_centroids):
        best_tid = None
        best_dist = float('inf')
        for tid, tdata in track_items:
            if tid in matched_tracks:
                continue
            dist = euclid(det_c, tdata['centroid'])
            if dist < best_dist:
                best_dist = dist
                best_tid = tid
        if best_tid is not None and best_dist <= MAX_MATCH_DIST:
            # match detected
            x, y, w, h, area, mean_int = detections[di]
            tracks[best_tid]['bbox'] = (x, y, w, h)
            tracks[best_tid]['centroid'] = det_centroids[di]
            # If last_seen was previous frame, increment consecutive, else set to 1
            if frame_idx - tracks[best_tid]['last_seen'] == 1:
                tracks[best_tid]['consecutive'] += 1
            else:
                tracks[best_tid]['consecutive'] = 1
            tracks[best_tid]['last_seen'] = frame_idx
            matched_tracks.add(best_tid)
            unmatched_dets.discard(di)

    # Create new tracks for unmatched detections
    for di in list(unmatched_dets):
        x, y, w, h, area, mean_int = detections[di]
        cid = next_track_id
        next_track_id += 1
        tracks[cid] = {
            'bbox': (x, y, w, h),
            'centroid': det_centroids[di],
            'first_seen': frame_idx,
            'last_seen': frame_idx,
            'consecutive': 1,
            'counted': False
        }

    # Check confirmation: if any track reached CONFIRM_FRAMES and not yet counted -> count it
    for tid, tdata in list(tracks.items()):
        if (not tdata['counted']) and (tdata['consecutive'] >= CONFIRM_FRAMES):
            tdata['counted'] = True
            unique_pothole_count += 1
            # Only print when we confirm a stable new pothole
            print("signal----------")
            print(f"Confirmed pothole id={tid} at frame {frame_idx} (seen {tdata['consecutive']} consecutive frames).")

    # Remove stale tracks
    to_delete = []
    for tid, tdata in tracks.items():
        if frame_idx - tdata['last_seen'] > MAX_LOST_FRAMES:
            to_delete.append(tid)
    for tid in to_delete:
        del tracks[tid]

    # 6) Draw detections (convert coords back to full frame)
    for (x, y, w, h, area, mean_int) in detections:
        top_left = (x, y + y_start)
        bottom_right = (x + w, y + h + y_start)
        cv2.rectangle(frame, top_left, bottom_right, (0, 0, 255), 2)
        label = f"Pothole? A={int(area)} I={int(mean_int)}"
        cv2.putText(frame, label, (top_left[0], max(top_left[1]-6,0)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,255), 1, cv2.LINE_AA)

    # Optional: draw active tracks and their status (counted or not) — lightly helpful for debugging
    for tid, tdata in tracks.items():
        x, y, w, h = tdata['bbox']
        tl = (int(x), int(y + y_start))
        br = (int(x + w), int(y + h + y_start))
        color = (0,255,0) if tdata['counted'] else (255,165,0)  # green if counted, orange otherwise
        cv2.rectangle(frame, tl, br, color, 1)
        cv2.putText(frame, f"id{tid} c{tdata['consecutive']}", (tl[0], max(tl[1]-8,0)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

    cv2.imshow('Pothole Detector - Press ESC or Q to quit', frame)
    key = cv2.waitKey(delay) & 0xFF
    if key == 27 or key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
print("Done. Processed {} frames. Final confirmed potholes: {}.".format(frame_idx, unique_pothole_count))
