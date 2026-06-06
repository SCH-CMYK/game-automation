"""
小地图导航模块 — 模板匹配驱动，零训练
"""
import cv2, numpy as np, math, time
from pathlib import Path


class MinimapNav:
    """小地图矿石追踪"""

    def __init__(self, template_dir: str = None):
        self.templates = {}  # name -> image
        self.minimap_region = None  # (x, y, w, h) 屏幕坐标
        self.arrow_template = None  # 箭头模板
        self._last_ore_icon_pos = None

    # === 模板管理 ===
    def set_region(self, x: int, y: int, w: int, h: int):
        self.minimap_region = (x, y, w, h)

    def load_arrow(self, image_path: str):
        self.arrow_template = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    def load_ore_icon(self, image_path: str, name: str = "ore"):
        self.templates[name] = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)

    # === 小地图提取 ===
    def grab_minimap(self, screenshot: np.ndarray):
        if not self.minimap_region:
            return None
        x, y, w, h = self.minimap_region
        return screenshot[y:y+h, x:x+w]

    # === 矿石图标检测 ===
    def find_ore_on_minimap(self, minimap_img: np.ndarray):
        """在小地图上找矿石图标，返回最优先目标"""
        if not self.templates:
            return None

        gray = cv2.cvtColor(minimap_img, cv2.COLOR_BGR2GRAY) if len(minimap_img.shape) == 3 else minimap_img

        best = None
        for name, tmpl in self.templates.items():
            h, w = tmpl.shape[:2]
            result = cv2.matchTemplate(gray, tmpl, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)
            if max_val > 0.7:
                cx = max_loc[0] + w // 2
                cy = max_loc[1] + h // 2
                best = {"name": name, "pos": (cx, cy), "conf": max_val,
                        "bbox": (max_loc[0], max_loc[1], max_loc[0] + w, max_loc[1] + h)}
                break  # 取置信度最高的第一个
        return best

    # === 方向计算 ===
    def calc_direction(self, minimap_img: np.ndarray, target_pos: tuple):
        """算箭头到目标的水平旋转角度(px)"""
        if not self.arrow_template or self.minimap_region is None:
            return None

        gray = cv2.cvtColor(minimap_img, cv2.COLOR_BGR2GRAY) if len(minimap_img.shape) == 3 else minimap_img

        # 找箭头
        h, w = self.arrow_template.shape[:2]
        result = cv2.matchTemplate(gray, self.arrow_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val < 0.6:
            return None
        arrow_cx = max_loc[0] + w // 2
        arrow_cy = max_loc[1] + h // 2

        # 算方向向量
        tx, ty = target_pos
        dx = tx - arrow_cx
        dy = ty - arrow_cy
        angle = math.degrees(math.atan2(-dx, -dy))  # 转成游戏世界的方向

        # 转成鼠标移动量（粗略：小地图每像素约对应 N 度视角）
        turn_px = int(dx * -3)  # 负号是因为屏幕坐标 y 轴向下
        return {
            "arrow_pos": (arrow_cx, arrow_cy),
            "target": target_pos,
            "dx": dx, "dy": dy,
            "angle": angle,
            "turn_px": turn_px,
            "dist_mm": math.hypot(dx, dy),  # 小地图上的距离
        }

    # === 图标消失检测 ===
    def is_ore_gone(self, minimap_img: np.ndarray):
        """矿石图标还在不在"""
        ore = self.find_ore_on_minimap(minimap_img)
        if ore is None:
            return True
        # 和上次位置对比，如果彻底没了就是采完了
        if self._last_ore_icon_pos:
            dist = math.hypot(ore["pos"][0] - self._last_ore_icon_pos[0],
                              ore["pos"][1] - self._last_ore_icon_pos[1])
            if dist > 50:  # 移动超过 50px = 另一个矿
                return True
        self._last_ore_icon_pos = ore["pos"]
        return False
