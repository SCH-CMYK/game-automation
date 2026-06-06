"""
小地图圆形框选工具

操作：
- 鼠标移动：圆形跟随
- 左键拖动：移动圆形
- 滚轮：调整大小
- 回车/双击：确认
- ESC：取消
"""
import cv2
import numpy as np


class MinimapSelector:
    """圆形框选小地图"""

    def __init__(self):
        self.cx = 960  # 圆心 x
        self.cy = 540  # 圆心 y
        self.radius = 90  # 半径
        self.dragging = False
        self.drag_offset = (0, 0)
        self.confirmed = False
        self.cancelled = False

    def select(self, frame):
        """在截图上框选小地图

        Args:
            frame: BGR 截图 (numpy array)

        Returns:
            (x, y, w, h) 裁剪区域，或 None（取消）
        """
        self.frame = frame.copy()
        self.display = frame.copy()
        h, w = frame.shape[:2]

        # 初始位置：右上角（小地图通常在这里）
        self.cx = w - 180
        self.cy = 180
        self.radius = 90

        win_name = "Minimap Selector - Drag/Wheel/Enter/Esc"
        cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win_name, min(w, 1280), min(h, 720))
        cv2.setMouseCallback(win_name, self._mouse_cb)

        while not self.confirmed and not self.cancelled:
            self.display = self.frame.copy()

            # 画圆形选区
            cv2.circle(self.display, (self.cx, self.cy), self.radius, (0, 255, 0), 2)
            # 画十字准星
            cv2.line(self.display, (self.cx - 15, self.cy), (self.cx + 15, self.cy), (0, 255, 0), 1)
            cv2.line(self.display, (self.cx, self.cy - 15), (self.cx, self.cy + 15), (0, 255, 0), 1)
            # 显示尺寸信息
            info = f"center=({self.cx},{self.cy}) r={self.radius} size={self.radius*2}x{self.radius*2}"
            cv2.putText(self.display, info, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(self.display, "Drag=Move  Wheel=Resize  Enter/Double=OK  Esc=Cancel",
                        (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)

            cv2.imshow(win_name, self.display)
            key = cv2.waitKey(16) & 0xFF  # ~60 FPS

            if key == 13:  # Enter
                self.confirmed = True
            elif key == 27:  # Esc
                self.cancelled = True
            elif key == ord('+') or key == ord('='):
                self.radius = min(200, self.radius + 5)
            elif key == ord('-'):
                self.radius = max(30, self.radius - 5)

        cv2.destroyAllWindows()

        if self.confirmed:
            # 返回正方形裁剪区域（圆形外接矩形）
            x = max(0, self.cx - self.radius)
            y = max(0, self.cy - self.radius)
            size = self.radius * 2
            return (x, y, size, size)
        return None

    def _mouse_cb(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            # 检查是否在圆内
            dist = ((x - self.cx) ** 2 + (y - self.cy) ** 2) ** 0.5
            if dist <= self.radius:
                self.dragging = True
                self.drag_offset = (x - self.cx, y - self.cy)
            else:
                # 点击圆外 → 移动圆心到点击位置
                self.cx = x
                self.cy = y

        elif event == cv2.EVENT_MOUSEMOVE:
            if self.dragging:
                self.cx = x - self.drag_offset[0]
                self.cy = y - self.drag_offset[1]

        elif event == cv2.EVENT_LBUTTONUP:
            self.dragging = False

        elif event == cv2.EVENT_LBUTTONDBLCLK:
            self.confirmed = True

        elif event == cv2.EVENT_MOUSEWHEEL:
            if flags > 0:
                self.radius = min(200, self.radius + 5)
            else:
                self.radius = max(30, self.radius - 5)


def select_minimap(frame):
    """便捷函数：弹出框选界面，返回区域"""
    selector = MinimapSelector()
    return selector.select(frame)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        img = cv2.imread(sys.argv[1])
    else:
        # 截取当前屏幕
        import mss
        with mss.mss() as sct:
            img = np.array(sct.grab(sct.monitors[1]))[:, :, :3]

    if img is not None:
        region = select_minimap(img)
        if region:
            x, y, w, h = region
            print(f"Selected: x={x}, y={y}, w={w}, h={h}")
            # 保存预览
            crop = img[y:y+h, x:x+w]
            cv2.imwrite("minimap_preview.png", crop)
            print(f"Preview saved: minimap_preview.png")
        else:
            print("Cancelled")
