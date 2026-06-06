"""鼠标位置获取 — 右键点击获取坐标"""
from ctypes import windll, Structure, c_long, byref

class POINT(Structure):
    _fields_ = [("x", c_long), ("y", c_long)]

user32 = windll.user32

print("右键点击'是'按钮获取坐标，按 Enter 退出\n")

try:
    while True:
        # 检测右键按下 (VK_RBUTTON = 0x02)
        if user32.GetAsyncKeyState(0x02) & 0x8000:
            pt = POINT()
            user32.GetCursorPos(byref(pt))
            print(f"YES button: ({pt.x}, {pt.y})")
            import time
            time.sleep(0.3)  # 防重复触发

        # Enter 退出
        if user32.GetAsyncKeyState(0x0D) & 0x8000:
            break

except KeyboardInterrupt:
    pass
