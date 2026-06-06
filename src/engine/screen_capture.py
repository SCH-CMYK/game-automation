"""
屏幕截图模块 - 全屏/区域截图、实时帧流
"""
import time
import threading
from typing import Optional, Generator

import cv2
import numpy as np
import mss


class ScreenCapture:
    def __init__(self, monitor_index: int = 1):
        self.sct = mss.mss()
        self.monitors = self.sct.monitors  # [0]=全屏合并, [1]=主显示器, [2+]=副显示器
        if monitor_index >= len(self.monitors):
            monitor_index = 0
        self.monitor = self.monitors[monitor_index]
        self.monitor_index = monitor_index
        self._lock = threading.Lock()   # 防多线程死锁

    def list_monitors(self):
        result = []
        for i, m in enumerate(self.monitors):
            result.append({
                "index": i,
                "left": m["left"], "top": m["top"],
                "width": m["width"], "height": m["height"],
            })
        return result

    def grab(self, region: Optional[dict] = None):
        """截取屏幕，返回 BGR numpy array（线程安全）"""
        if region is None:
            region = self.monitor
        with self._lock:
            img = self.sct.grab(region)
        return cv2.cvtColor(np.array(img), cv2.COLOR_BGRA2BGR)

    def grab_rect(self, left: int, top: int, width: int, height: int):
        """截取矩形区域"""
        return self.grab({"left": left, "top": top, "width": width, "height": height})

    def stream(self, region: Optional[dict] = None, fps: int = 30):
        """实时截图流"""
        interval = 1.0 / fps
        while True:
            start = time.perf_counter()
            yield self.grab(region)
            elapsed = time.perf_counter() - start
            if elapsed < interval:
                time.sleep(interval - elapsed)

    @property
    def size(self):
        return (self.monitor["width"], self.monitor["height"])

    @property
    def left(self):
        return self.monitor["left"]

    @property
    def top(self):
        return self.monitor["top"]
