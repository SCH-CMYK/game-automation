"""查看图片像素坐标 — 拖入图片，鼠标移到目标位置看坐标"""
import cv2, sys

if len(sys.argv) < 2:
    print("用法: python view_image.py image.png")
    print("或直接把图片拖到 view_image.py 上")
    sys.exit(1)

img = cv2.imread(sys.argv[1])
h, w = img.shape[:2]
print(f"图片尺寸: {w}x{h}")
print("鼠标移到目标位置看坐标，按 ESC 退出")

def on_mouse(event, x, y, flags, param):
    if event == cv2.EVENT_MOUSEMOVE:
        b, g, r = img[y, x] if 0 <= y < h and 0 <= x < w else (0,0,0)
        print(f"\r坐标: ({x}, {y})  颜色: R={r} G={g} B={b}", end="  ")

cv2.namedWindow("Image", cv2.WINDOW_NORMAL)
cv2.resizeWindow("Image", min(w, 1400), min(h, 900))
cv2.setMouseCallback("Image", on_mouse)

while cv2.waitKey(50) & 0xFF != 27:  # ESC 退出
    cv2.imshow("Image", img)

cv2.destroyAllWindows()
