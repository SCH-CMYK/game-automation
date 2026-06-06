"""
测试 fixtures — Mock Capture/Controller/VisionEngine
"""
import sys
import threading
from pathlib import Path
import numpy as np
import cv2

sys.path.insert(0, str(Path(__file__).parent.parent))


class MockCapture:
    """返回合成游戏帧（1280x720 BGR 全黑图，带白色"矿"块）"""

    def __init__(self):
        self.sct = None  # 不需要真正的 mss
        self.frame = np.zeros((720, 1280, 3), dtype=np.uint8)
        # 画一个白色方块模拟矿石
        cv2.rectangle(self.frame, (600, 340), (680, 380), (255, 255, 255), -1)

    def grab(self, region=None):
        return self.frame.copy()

    @property
    def size(self):
        return (1280, 720)


class MockController:
    """记录所有输入调用，不执行实际操作"""

    def __init__(self):
        self.calls = []       # [(method, args), ...]
        self._held = set()    # 当前按住的键
        self._lock = threading.Lock()

    def acquire_lock(self):
        self._lock.acquire()

    def release_lock(self):
        self._lock.release()

    def __enter__(self):
        self.acquire_lock()
        return self

    def __exit__(self, *args):
        self.release_lock()

    def key_down(self, key):
        self.calls.append(('key_down', key))
        self._held.add(key)

    def key_up(self, key):
        self.calls.append(('key_up', key))
        self._held.discard(key)

    def move_relative(self, dx, dy=0):
        self.calls.append(('move_relative', dx, dy))

    def mouse_down(self, button='left'):
        self.calls.append(('mouse_down', button))

    def mouse_up(self, button='left'):
        self.calls.append(('mouse_up', button))

    def press(self, key, duration=0.08):
        self.calls.append(('press', key))

    def reset(self):
        self.calls.clear()
        self._held.clear()


class MockVision:
    """返回可配置的假检测结果"""

    def __init__(self):
        self.loaded = True
        self.names = {0: 'ore', 1: 'creature', 2: 'obstacle', 3: 'character'}
        # 默认：画面中心有一个矿石
        self._fake_dets = {
            "ore": [{
                "bbox": (610, 350, 670, 370),
                "center": (640, 360),
                "confidence": 0.9,
                "class": "ore",
                "area": 1200,
                "cls_id": 0,
            }],
            "creature": [],
            "obstacle": [],
            "character": [],
        }

    def detect_all(self, image, conf=0.3, iou=0.5):
        return self._fake_dets.copy()

    def find_best_ore(self, image):
        ores = self._fake_dets.get("ore", [])
        return ores[0] if ores else None

    def is_path_blocked(self, image):
        return len(self._fake_dets.get("obstacle", [])) > 0

    def set_ore(self, ore_list):
        """配置假矿石检测结果"""
        self._fake_dets["ore"] = ore_list

    def set_creature(self, creature_list):
        self._fake_dets["creature"] = creature_list

    def set_obstacle(self, obstacle_list):
        self._fake_dets["obstacle"] = obstacle_list

    def set_character(self, char_list):
        self._fake_dets["character"] = char_list

    def clear_all(self):
        for k in self._fake_dets:
            self._fake_dets[k] = []
