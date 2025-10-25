"""
stable_text_display_tts_fixed.py
Fixed version: resolves camera/window issues, slicing bugs, and improves stability
"""

import cv2
import easyocr
import numpy as np
import time
import threading
import queue
from collections import deque, Counter
import pyttsx3

# -----------------------
# Configuration
# -----------------------
CAM_INDEX = 0
FRAME_SKIP = 3
DOWNSCALE = 0.5
CONF_THRESHOLD = 0.4
DETECTION_HISTORY = 5
REQUIRED_AGREE = 2
SPEECH_THROTTLE_SEC = 2
DRAW_BOXES = True
# -----------------------

frame_queue = queue.Queue(maxsize=2)
result_queue = queue.Queue()
stop_event = threading.Event()

def ocr_worker(frame_q: queue.Queue, res_q: queue.Queue, stop_evt: threading.Event):
    """OCR worker thread that processes frames"""
    reader = easyocr.Reader(['en'], gpu=False)
    while not stop_evt.is_set():
        try:
            small_rgb = frame_q.get(timeout=0.2)
        except queue.Empty:
            continue
        try:
            results = reader.readtext(small_rgb)
        except Exception:
            res_q.put(([], "", time.time()))
            continue

        filtered = []
        for bbox, text, conf in results:
            if conf >= CONF_THRESHOLD:
                clean = text.strip()
                if clean:
                    filtered.append((bbox, clean, float(conf)))

        if filtered:
            def bbox_center(b):
                xs = [p[0] for p in b]
                ys = [p[1] for p in b]
                return (sum(xs) / len(xs), sum(ys) / len(ys))
            filtered_sorted = sorted(filtered, key=lambda it: (bbox_center(it[0])[1], bbox_center(it[0])[0]))
            joined = " ".join([it[1] for it in filtered_sorted])
        else:
            joined = ""

        res_q.put((filtered, joined, time.time()))

def speak_text(engine, text):
    """Speak text using TTS engine"""
    if not text:
        return
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print(f"TTS error: {e}")

def main():
    # Initialize TTS
    tts = pyttsx3.init()
    
    # Start OCR worker thread
    worker = threading.Thread(target=ocr_worker, args=(frame_queue, result_queue, stop_event), daemon=True)
    worker.start()

    # Initialize camera with better settings
    cap = cv2.VideoCapture(CAM_INDEX)
    
    # Set camera properties for better performance
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    
    if not cap.isOpened():
        print(f"ERROR: Cannot open camera {CAM_INDEX}")
        print("Tips:")
        print("1. Check if camera is connected")
        print("2. Try different CAM_INDEX values (0, 1, 2)")
        print("3. Close other apps using the camera")
        return

    # Verify camera is actually working
    ret, test_frame = cap.read()
    if not ret or test_frame is None:
        print("ERROR: Camera opened but cannot read frames")
        cap.release()
        return
    
    print(f"Camera initialized: {test_frame.shape[1]}x{test_frame.shape[0]}")

    # Create window (simple approach for Windows compatibility)
    window_name = "Stable Text OCR + TTS (Press Q to quit, C to clear)"
    try:
        cv2.namedWindow(window_name, cv2.WINDOW_AUTOSIZE)
    except:
        # If namedWindow fails, we'll just use imshow directly
        pass

    frame_count = 0
    last_text = ""
    history = deque(maxlen=DETECTION_HISTORY)
    last_spoken_time = 0
    last_filtered = []
    prev_time = time.time()
    fps = 0.0

    print("\nControls:")
    print("  Q - Quit")
    print("  C - Clear detected text")
    print("\nStarting main loop...\n")

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                print("WARNING: Frame read failed")
                time.sleep(0.1)
                continue

            frame_count += 1

            # Send frame to OCR worker
            if frame_count % FRAME_SKIP == 0:
                small = cv2.resize(frame, (0, 0), fx=DOWNSCALE, fy=DOWNSCALE)
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                try:
                    frame_queue.put_nowait(rgb)
                except queue.Full:
                    pass

            # Get OCR results
            try:
                while True:
                    filtered, joined_text, ts = result_queue.get_nowait()
                    history.append(joined_text)
                    last_filtered = filtered
            except queue.Empty:
                pass

            # Determine stable text
            candidate_text = ""
            if history:
                counts = Counter(history)
                candidate_text, cnt = counts.most_common(1)[0]
                if candidate_text and (candidate_text != last_text) and cnt >= REQUIRED_AGREE:
                    last_text = candidate_text
                    print(f"[Detected]: {last_text}")
                    now = time.time()
                    if now - last_spoken_time >= SPEECH_THROTTLE_SEC:
                        speak_text(tts, last_text)
                        last_spoken_time = now

            display_text = str(last_text) if last_text else ""

            # Create overlay for drawing
            overlay = frame.copy()
            
            # Draw bounding boxes
            if DRAW_BOXES and last_filtered:
                for bbox, text, conf in last_filtered:
                    pts = np.array(bbox, dtype=np.float32)
                    pts = (pts / DOWNSCALE).astype(np.int32)
                    cv2.polylines(overlay, [pts.reshape((-1, 1, 2))], isClosed=True, color=(0, 255, 0), thickness=2)
                    x_min = int(np.min(pts[:, 0]))
                    y_min = int(np.min(pts[:, 1])) - 6
                    cv2.putText(overlay, f"{text} ({conf:.2f})", (x_min, max(y_min, 10)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

            alpha = 0.9
            frame = cv2.addWeighted(overlay, alpha, frame, 1 - alpha, 0)

            # Calculate FPS
            cur_time = time.time()
            dt = cur_time - prev_time if cur_time - prev_time > 1e-6 else 1e-6
            prev_time = cur_time
            fps = 0.9 * fps + 0.1 * (1.0 / dt)

            # Draw FPS
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 0, 0), 2)

            # Draw detected text with word wrapping
            max_chars_per_line = 50
            if display_text:
                lines = [display_text[i:i+max_chars_per_line] for i in range(0, len(display_text), max_chars_per_line)]
            else:
                lines = ["No text detected"]

            y0 = 70
            for idx, line in enumerate(lines):
                cv2.putText(frame, line, (10, y0 + idx * 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

            # Display frame
            cv2.imshow(window_name, frame)

            # Handle keyboard input
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q') or key == ord('Q') or key == 27:  # Q or ESC
                print("\nExiting...")
                break
            if key == ord('c') or key == ord('C'):
                last_text = ""
                history.clear()
                print("[Text cleared]")

    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
    finally:
        print("Cleaning up...")
        stop_event.set()
        time.sleep(0.3)
        cap.release()
        cv2.destroyAllWindows()
        # Force destroy window
        cv2.waitKey(1)
        print("Exited cleanly")

if __name__ == "__main__":
    main()