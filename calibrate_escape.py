"""
Calibrate escape button position.
Usage:
  1. Enter game, press ESC to show the exit confirmation dialog
  2. Run: python calibrate_escape.py
  3. Click the "YES" button in the image window (a red dot marks your click)
  4. Press ENTER key to confirm
  5. To retry: just click again before pressing ENTER
  6. Position saved to escape_position.json
"""
import json
from pathlib import Path

import cv2
import mss
import numpy as np

PROJECT_DIR = Path(__file__).parent.resolve()
SAVE_FILE = PROJECT_DIR / "escape_position.json"

click_pos = None


def on_mouse(event, x, y, flags, param):
    global click_pos
    if event == cv2.EVENT_LBUTTONDOWN:
        click_pos = (x, y)


def main():
    global click_pos

    # Capture screen
    with mss.mss() as sct:
        monitor = sct.monitors[1]
        img = np.array(sct.grab(monitor))
        img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

    h, w = img.shape[:2]
    display_w = min(w, 1280)
    scale = display_w / w
    display_h = int(h * scale)
    display = cv2.resize(img, (display_w, display_h))

    win_name = "Click the YES button, then press ENTER"
    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win_name, on_mouse)

    print("Click the 'YES' button in the image window, then press ENTER.")
    print("(Click again to reposition, ENTER to confirm, ESC to cancel)")

    while True:
        frame = display.copy()
        if click_pos is not None:
            cv2.circle(frame, click_pos, 8, (0, 0, 255), -1)
            cv2.circle(frame, click_pos, 12, (0, 0, 255), 2)
            cv2.putText(frame, f" ({click_pos[0]}, {click_pos[1]})",
                        (click_pos[0] + 15, click_pos[1] - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
        cv2.imshow(win_name, frame)
        key = cv2.waitKey(50) & 0xFF
        if key == 13:  # ENTER
            break
        if key == 27:  # ESC
            click_pos = None
            break

    cv2.destroyAllWindows()

    if click_pos is None:
        print("[CANCEL] No position saved. Using default 5-position fallback.")
        return

    real_x = int(click_pos[0] / scale)
    real_y = int(click_pos[1] / scale)
    print(f"Saved: ({real_x}, {real_y}) at {w}x{h}")

    data = {"screen_w": w, "screen_h": h, "positions": [{"x": real_x, "y": real_y}]}
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"File: {SAVE_FILE}")


if __name__ == "__main__":
    main()
