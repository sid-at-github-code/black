# minimal_ocr_tts_reinit.py
# Bare-minimum OCR + immediate TTS. Re-initializes TTS engine per utterance to avoid "only-first-word" bugs.

import cv2
import easyocr
import time
import sys

CAM_INDEX = 0
FRAME_SKIP = 3
DOWNSCALE = 0.5
CONF_THRESHOLD = 0.4

reader = easyocr.Reader(['en'], gpu=False)

cap = cv2.VideoCapture(CAM_INDEX)
if not cap.isOpened():
    raise RuntimeError("Cannot open camera")

last_text = ""
frame_count = 0

def speak_now(text: str):
    """Create a fresh pyttsx3 engine each time, speak, then try to clean up."""
    try:
        import pyttsx3
        engine = pyttsx3.init()
        engine.say(text)
        engine.runAndWait()
        try:
            engine.stop()
        except Exception:
            pass
        try:
            del engine
        except Exception:
            pass
    except Exception as e:
        print("TTS error (speak_now):", e)

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Camera read failed, exiting.")
            break

        frame_count += 1
        if frame_count % FRAME_SKIP != 0:
            time.sleep(0.01)
            continue

        small = cv2.resize(frame, (0,0), fx=DOWNSCALE, fy=DOWNSCALE)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)

        try:
            results = reader.readtext(rgb)
        except Exception as e:
            print("OCR error:", e)
            continue

        words = []
        for bbox, text, conf in results:
            if conf >= CONF_THRESHOLD:
                words.append(text.strip())

        detected = " ".join(words).strip()

        if detected and detected != last_text:
            last_text = detected
            print("[DETECTED]:", detected)
            # speak immediately — fresh engine per utterance
            speak_now(detected)

        # Optional: show single-line overlay if your OpenCV supports imshow.
        # If not, remove below block (or run headless).
        try:
            cv2.putText(frame, last_text, (10,50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)
            cv2.imshow("Minimal OCR+TTS (reinit)", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
        except Exception:
            # headless environment: ignore imshow errors
            pass

except KeyboardInterrupt:
    print("\nInterrupted by user.")
finally:
    try:
        cap.release()
    except Exception:
        pass
    try:
        cv2.destroyAllWindows()
    except Exception:
        pass
    print("Exited cleanly.")
    sys.exit(0)
