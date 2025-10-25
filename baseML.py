
import cv2
import numpy as np

VIDEO_IN  = "pothole_road_sample1.mp4"

# TUNABLE PARAMETERS (start with these; tweak if many false+ or misses)
MIN_AREA        = 6000     
MAX_AREA        = 40000    
DARK_MEAN_THRESH= 200      
ASPECT_RATIO_MIN= 1.2       
ASPECT_RATIO_MAX= 3.2
ROI_Y_START_FRAC = 0.35    


# Background subtractor helps isolate transient road defects
bg_sub = cv2.createBackgroundSubtractorMOG2(history=200, varThreshold=50, detectShadows=False)

cap = cv2.VideoCapture(VIDEO_IN)
if not cap.isOpened():
    raise SystemExit("Cannot open video file: " + VIDEO_IN)

W  = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H  = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7,7))

print("Processing live... Press ESC or 'q' to quit")
fps = cap.get(cv2.CAP_PROP_FPS)
speed = 0.8
delay = int((1000 / fps)*speed) 

frame_idx = 0
while True:
    ret, frame = cap.read()
    if not ret:
        break
    frame_idx += 1

    # 1) ROI crop (focus on lower part of frame where road/potholes appear)
    y_start = int(H * ROI_Y_START_FRAC)
    roi = frame[y_start:H, 0:W]

    # 2) Preprocess: gray, blur, equalize
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    gray_blur = cv2.GaussianBlur(gray, (7,7), 0)
    # Optional contrast boost for darker holes
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    gray_eq = clahe.apply(gray_blur)

    # 3) Background subtraction (helps remove static road texture after some frames)
    fg = bg_sub.apply(gray_eq)
    # clean noise
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, kernel, iterations=1)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 4) Edge + dark region detection combined (Canny + threshold)
    edges = cv2.Canny(gray_eq, 60, 140)
    _, dark = cv2.threshold(gray_eq, DARK_MEAN_THRESH, 255, cv2.THRESH_BINARY_INV)

    # combine masks: areas that are dark AND have some foreground motion/contrast
    combined = cv2.bitwise_and(fg, dark)
    combined = cv2.bitwise_or(combined, edges)  # include strong edges
    # more morphology to fill holes
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
        # solidity filter: area / bounding_box_area (low solidity might be many tiny bits -> ignore)
        bbox_area = w * h
        solidity = float(area) / (bbox_area + 1e-6)
        if solidity < 0.2:
            continue
        # mean intensity inside bounding box (within roi coords)
        roi_patch = gray_eq[y:y+h, x:x+w]
        mean_int = float(np.mean(roi_patch)) if roi_patch.size else 255
        if mean_int > DARK_MEAN_THRESH + 20:  # ensure significantly dark
            continue

        # Passed heuristics -> consider as pothole candidate
        detections.append((x, y, w, h, area, mean_int))

    # 6) Draw detections (convert coords back to full frame)
    for (x, y, w, h, area, mean_int) in detections:
        top_left = (x, y + y_start)
        bottom_right = (x + w, y + h + y_start)
        cv2.rectangle(frame, top_left, bottom_right, (0, 0, 255), 2)  # RED box
        label = f"Pothole? A={int(area)} I={int(mean_int)}"
        cv2.putText(frame, label, (top_left[0], max(top_left[1]-6,0)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0,0,255), 1, cv2.LINE_AA)

    cv2.imshow('Pothole Detector - Press ESC or Q to quit', frame)
    key = cv2.waitKey(delay) & 0xFF
    if key == 27 or key == ord('q'):  # ESC or 'q' to quit
        break

cap.release()
cv2.destroyAllWindows()
print("Done. Processed {} frames.".format(frame_idx))