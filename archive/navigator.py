"""
地图路线导航模块
- 分析用户上传的地图 + 手绘路线 → 提取途经点
- 小地图追踪玩家位置
- 按路线自动导航：走到途经点 → 扫描采集 → 下一个点
"""
import time
import math
from typing import Optional, List, Tuple
from dataclasses import dataclass, field

import cv2
import numpy as np


# ============================================================
# 数据结构
# ============================================================

@dataclass
class Waypoint:
    """途经点"""
    x: int                          # 地图上的 x 坐标
    y: int                          # 地图上的 y 坐标
    label: str = ""                 # 标签
    walk_key: str = "w"             # 走到这个点按什么键
    walk_duration: float = 2.0      # 走多久（秒）
    mine_duration: float = 10.0     # 在此处采矿多久（0=不采矿）
    mined: bool = False             # 是否已采集过


@dataclass
class Route:
    """路线"""
    name: str = "默认路线"
    waypoints: List[Waypoint] = field(default_factory=list)
    loop: bool = False              # 是否循环


# ============================================================
# 地图路线分析
# ============================================================

class MapAnalyzer:
    """分析用户上传的地图图片，提取手绘路线"""

    # 常见手绘路线颜色 HSV 范围
    COLOR_RANGES = {
        "red":    (np.array([0, 60, 60]),   np.array([10, 255, 255])),
        "red2":   (np.array([160, 60, 60]), np.array([180, 255, 255])),
        "blue":   (np.array([100, 60, 60]), np.array([130, 255, 255])),
        "green":  (np.array([40, 60, 60]),  np.array([80, 255, 255])),
        "yellow": (np.array([20, 60, 60]),  np.array([35, 255, 255])),
        "black":  (np.array([0, 0, 0]),     np.array([180, 255, 60])),
    }

    @staticmethod
    def extract_route_line(map_image: np.ndarray, line_color: str = "red") -> Optional[np.ndarray]:
        """
        从地图图片中提取手绘路线，返回路线的二值 mask
        """
        hsv = cv2.cvtColor(map_image, cv2.COLOR_BGR2HSV)

        # 合并两个红色范围（红色在 HSV 两头）
        mask = None
        if line_color == "red":
            mask1 = cv2.inRange(hsv, *MapAnalyzer.COLOR_RANGES["red"])
            mask2 = cv2.inRange(hsv, *MapAnalyzer.COLOR_RANGES["red2"])
            mask = cv2.bitwise_or(mask1, mask2)
        elif line_color in MapAnalyzer.COLOR_RANGES:
            mask = cv2.inRange(hsv, *MapAnalyzer.COLOR_RANGES[line_color])
        else:
            return None

        # 形态学操作去噪 + 连接断裂
        kernel = np.ones((3, 3), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        return mask

    @staticmethod
    def mask_to_waypoints(mask: np.ndarray, num_points: int = 10,
                          sort_order: str = "path") -> List[Tuple[int, int]]:
        """
        将路线 mask 转换为有序途经点列表
        sort_order: "path" 按路线方向排序 / "grid" 按网格排序
        """
        # 找到所有路线像素
        ys, xs = np.where(mask > 0)
        if len(xs) == 0:
            return []

        points = list(zip(xs, ys))

        if sort_order == "grid":
            # 简单均匀采样
            step = max(1, len(points) // num_points)
            return points[::step][:num_points]

        # "path" 排序：从路线一端走到另一端
        return MapAnalyzer._order_along_path(points, num_points)

    @staticmethod
    def _order_along_path(points: List[Tuple[int, int]],
                          num_points: int) -> List[Tuple[int, int]]:
        """
        沿路径排序：找到端点，然后沿着路径追踪
        """
        if len(points) < 2:
            return points[:num_points]

        # 转成 set 便于查找邻居
        point_set = set(points)

        def neighbors(pt, radius=3):
            """找到 pt 附近的路线点"""
            nb = []
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if dx == 0 and dy == 0:
                        continue
                    np_pt = (pt[0] + dx, pt[1] + dy)
                    if np_pt in point_set:
                        nb.append(np_pt)
            return nb

        # 找到端点（邻居最少的点）
        endpoints = sorted(points, key=lambda p: len(neighbors(p)))

        if not endpoints:
            return points[:num_points]

        # 从一端开始 BFS 排序
        start = endpoints[0]
        ordered = [start]
        visited = {start}

        current = start
        while len(ordered) < len(points):
            nbs = [n for n in neighbors(current) if n not in visited]
            if not nbs:
                # 找最近的未访问点（处理断裂）
                remaining = [p for p in points if p not in visited]
                if not remaining:
                    break
                current = min(remaining, key=lambda p: (p[0]-current[0])**2 + (p[1]-current[1])**2)
            else:
                current = nbs[0]
            ordered.append(current)
            visited.add(current)

        # 均匀采样 num_points 个点
        if len(ordered) <= num_points:
            return ordered

        step = (len(ordered) - 1) / (num_points - 1) if num_points > 1 else 1
        sampled = [ordered[int(i * step)] for i in range(num_points)]
        return sampled

    @staticmethod
    def detect_route_waypoints(map_path: str, line_color: str = "red",
                               num_points: int = 10) -> List[Tuple[int, int]]:
        """
        一键分析：读取地图 → 提取路线 → 返回途经点坐标
        """
        img = cv2.imread(map_path)
        if img is None:
            raise FileNotFoundError(f"地图文件不存在: {map_path}")

        mask = MapAnalyzer.extract_route_line(img, line_color)
        if mask is None or np.sum(mask) == 0:
            # 没检测到路线，降级为均匀网格采样
            print(f"未检测到 {line_color} 路线，请确认画线颜色。尝试自动检测...")
            # 尝试所有颜色
            for color in MapAnalyzer.COLOR_RANGES:
                mask = MapAnalyzer.extract_route_line(img, color)
                if mask is not None and np.sum(mask) > 50:
                    print(f"检测到 {color} 路线")
                    break

        if mask is None or np.sum(mask) == 0:
            raise ValueError("未能检测到任何路线。请用红色/蓝色/绿色笔在地图上画线。")

        points = MapAnalyzer.mask_to_waypoints(mask, num_points)
        return points

    @staticmethod
    def draw_waypoints_on_map(map_image: np.ndarray, waypoints: list) -> np.ndarray:
        """在地图上绘制途经点（用于预览）"""
        img = map_image.copy()
        colors = [
            (0, 0, 255),    # 起点红色
            (0, 255, 0),    # 中间绿色
            (255, 0, 0),    # 终点蓝色
        ]
        for i, wp in enumerate(waypoints):
            if isinstance(wp, Waypoint):
                x, y = wp.x, wp.y
                label = wp.label or str(i + 1)
            else:
                x, y = wp[0], wp[1]
                label = str(i + 1)

            if i == 0:
                color = colors[0]
            elif i == len(waypoints) - 1:
                color = colors[2]
            else:
                color = colors[1]

            cv2.circle(img, (x, y), 8, color, -1)
            cv2.putText(img, label, (x + 12, y + 5),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 画连接线
            if i > 0:
                prev = waypoints[i - 1]
                px, py = (prev.x, prev.y) if isinstance(prev, Waypoint) else (prev[0], prev[1])
                cv2.line(img, (px, py), (x, y), color, 2, cv2.LINE_AA)

        return img


# ============================================================
# 小地图追踪
# ============================================================

class MinimapTracker:
    """实时追踪小地图上的玩家位置"""

    def __init__(self):
        self.minimap_template = None     # 小地图模板（用于定位小地图在屏幕的位置）
        self.minimap_region = None       # 小地图在屏幕上的区域 (x, y, w, h)
        self.player_template = None      # 玩家标记模板（小地图上的箭头/圆点）
        self.last_player_pos = None      # 上次的玩家位置

    def set_minimap_region(self, x: int, y: int, w: int, h: int):
        """手动设置小地图区域"""
        self.minimap_region = (x, y, w, h)

    def find_minimap(self, screenshot: np.ndarray):
        """在截图中定位小地图（使用模板匹配）"""
        if self.minimap_template is None:
            return None
        from vision import TemplateMatcher
        result = TemplateMatcher.find(screenshot, self.minimap_template, threshold=0.7)
        if result:
            x, y, w, h, _ = result
            self.minimap_region = (x, y, w, h)
        return self.minimap_region

    def get_minimap(self, screenshot: np.ndarray) -> Optional[np.ndarray]:
        """截取小地图区域"""
        if self.minimap_region is None:
            return None
        x, y, w, h = self.minimap_region
        if (y + h > screenshot.shape[0] or x + w > screenshot.shape[1]):
            return None
        return screenshot[y:y+h, x:x+w]

    def find_player_on_minimap(self, minimap_img: np.ndarray) -> Optional[Tuple[int, int]]:
        """
        在小地图上找到玩家位置
        通常玩家标记是特殊颜色（如黄色箭头、绿色圆点）
        """
        if minimap_img is None:
            return None

        # 方法1：模板匹配（如果有玩家标记模板）
        if self.player_template is not None:
            from vision import TemplateMatcher
            result = TemplateMatcher.find(minimap_img, self.player_template, threshold=0.7)
            if result:
                x, y, w, h, _ = result
                self.last_player_pos = (x + w // 2, y + h // 2)
                return self.last_player_pos

        # 方法2：颜色检测（常见玩家标记颜色：黄色/白色高亮）
        hsv = cv2.cvtColor(minimap_img, cv2.COLOR_BGR2HSV)
        # 黄色
        yellow_mask = cv2.inRange(hsv, np.array([20, 80, 80]), np.array([35, 255, 255]))
        # 白色
        white_mask = cv2.inRange(hsv, np.array([0, 0, 200]), np.array([180, 30, 255]))
        combined = cv2.bitwise_or(yellow_mask, white_mask)

        contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            # 取最大的轮廓中心
            largest = max(contours, key=cv2.contourArea)
            M = cv2.moments(largest)
            if M["m00"] > 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                self.last_player_pos = (cx, cy)
                return (cx, cy)

        return self.last_player_pos

    def player_moved(self, threshold: int = 5) -> bool:
        """检测玩家是否在移动（小地图上标记是否在变化）"""
        # 简化版：始终返回 True（实际使用中可以记录最近 N 个位置判断变化幅度）
        return True


# ============================================================
# 路线导航引擎
# ============================================================

class RouteNavigator:
    """路线导航引擎：按路线走 → 采矿 → 下一站"""

    def __init__(self, route: Route, controller, capture, vision):
        self.route = route
        self.controller = controller
        self.capture = capture
        self.vision = vision
        self.tracker = MinimapTracker()

        self.running = False
        self.paused = False
        self.current_wp_idx = 0
        self.loop_count = 0
        self.stats = {
            "waypoints_visited": 0,
            "ores_clicked": 0,
            "loops_completed": 0,
        }

    # ---- 主循环 ----

    def run(self):
        """运行完整路线：每个途经点停下来采矿"""
        self.running = True
        self.current_wp_idx = 0

        while self.running and self.current_wp_idx < len(self.route.waypoints):
            wp = self.route.waypoints[self.current_wp_idx]
            print(f"\n📍 途经点 {self.current_wp_idx + 1}/{len(self.route.waypoints)}: {wp.label or str((wp.x, wp.y))}")

            # 1. 走到途经点
            self._walk_to_waypoint(wp)
            if not self.running:
                break

            # 2. 在途经点采矿
            if wp.mine_duration > 0:
                self._mine_at_waypoint(wp)

            # 3. 标记完成
            wp.mined = True
            self.stats["waypoints_visited"] += 1
            self.current_wp_idx += 1

        # 路线走完
        if self.route.loop and self.running:
            self.loop_count += 1
            self.stats["loops_completed"] += 1
            for wp in self.route.waypoints:
                wp.mined = False
            print(f"\n🔄 循环 #{self.loop_count}")

    def _walk_to_waypoint(self, wp: Waypoint):
        """走到途经点 — 按住指定方向键走指定时间"""
        if wp.walk_duration <= 0:
            return

        print(f"   🚶 按住 '{wp.walk_key}' 走 {wp.walk_duration:.1f} 秒...")
        self.controller.hold_key(wp.walk_key, wp.walk_duration)

    def _mine_at_waypoint(self, wp: Waypoint):
        """
        在当前途经点采矿：
        - 使用 YOLO/模板匹配扫描屏幕找矿石
        - 逐个点击采集
        - 直到矿采完或超时
        """
        print(f"   ⛏ 开始采矿 (最长 {wp.mine_duration:.0f} 秒)...")
        start_time = time.time()
        ores_in_area = 0

        while self.running:
            elapsed = time.time() - start_time
            if elapsed > wp.mine_duration:
                print(f"   ⏰ 采矿时间到，共采集 {ores_in_area} 个矿石")
                break

            if self.paused:
                time.sleep(0.1)
                continue

            # 截屏检测
            frame = self.capture.grab()
            detections = self.vision.find(frame)

            # 收集所有矿石目标
            targets = []
            for d in detections.get("yolo", []):
                if d["class"] == "ore" or d["class"] == self._target_class:
                    targets.append(d["center"])
            for name, matches in detections.get("templates", {}).items():
                for x, y, w, h, conf in matches:
                    targets.append((x + w // 2, y + h // 2))

            if targets:
                # 按距离排序，先采近的
                screen_cx = frame.shape[1] // 2
                screen_cy = frame.shape[0] // 2
                targets.sort(key=lambda p: (p[0]-screen_cx)**2 + (p[1]-screen_cy)**2)

                # 逐个点击（最多点击可见的前几个）
                for i, (tx, ty) in enumerate(targets[:5]):  # 最多点5个，避免一直点同一个
                    if not self.running:
                        break
                    print(f"      ⛏ 采集矿石 @ ({tx}, {ty})")
                    self.controller.click(tx, ty)
                    ores_in_area += 1
                    self.stats["ores_clicked"] += 1
                    time.sleep(0.5)  # 等待采矿动画
            else:
                # 没找到矿石，转转视角
                print(f"   🔍 扫描中... 未发现矿石，转动视角")
                self.controller.press('d', duration=0.3)
                time.sleep(0.3)

    # ---- 控制 ----

    def start(self, target_class: str = "ore"):
        self._target_class = target_class
        self.running = True
        import threading
        threading.Thread(target=self.run, daemon=True).start()

    def stop(self):
        self.running = False

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def skip_to_next(self):
        """跳过当前途经点"""
        if self.current_wp_idx < len(self.route.waypoints):
            # 设置 walk_duration 和 mine_duration 为 0 来加速跳过
            wp = self.route.waypoints[self.current_wp_idx]
            wp.walk_duration = 0.1
            wp.mine_duration = 0


# ============================================================
# 路线编辑器工具
# ============================================================

class RouteEditor:
    """辅助工具：在地图图片上手动点选途经点"""

    @staticmethod
    def manual_select(map_path: str, num_points: int = None, parent=None) -> List[Waypoint]:
        """
        打开地图让用户用鼠标点击途经点
        返回途经点列表
        """
        import tkinter as tk
        from tkinter import ttk
        from PIL import Image, ImageTk

        waypoints = []

        if parent:
            root = tk.Toplevel(parent)
        else:
            root = tk.Tk()
        root.title("在地图上点击途经点 → 按 Esc 完成")
        root.geometry("900x700")

        img_cv = cv2.imread(map_path)
        if img_cv is None:
            raise FileNotFoundError(f"地图文件不存在: {map_path}")
        img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        img_pil = Image.fromarray(img_rgb)

        # 缩放适配
        cw, ch = 860, 620
        scale = min(cw / img_pil.width, ch / img_pil.height)
        new_w, new_h = int(img_pil.width * scale), int(img_pil.height * scale)
        img_pil = img_pil.resize((new_w, new_h), Image.LANCZOS)

        canvas = tk.Canvas(root, width=new_w, height=new_h, cursor="cross")
        canvas.pack(pady=5)

        tk_img = ImageTk.PhotoImage(img_pil)
        canvas.create_image(0, 0, anchor=tk.NW, image=tk_img)

        status = ttk.Label(root, text="点击地图添加途经点，按 Esc 完成")
        status.pack()

        colors = ["#FF0000", "#00FF00", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF"]

        def on_click(event):
            # 映射回原始地图坐标
            ox = int(event.x / scale)
            oy = int(event.y / scale)
            i = len(waypoints)
            wp = Waypoint(x=ox, y=oy, label=f"点{i+1}")
            waypoints.append(wp)

            color = colors[i % len(colors)]
            r = 5
            canvas.create_oval(event.x-r, event.y-r, event.x+r, event.y+r,
                              fill=color, outline="white", width=1)
            canvas.create_text(event.x+10, event.y-10, text=str(i+1),
                              fill=color, font=("Arial", 10, "bold"))
            status.config(text=f"已添加 {len(waypoints)} 个途经点 | 按 Esc 完成 | 按 Z 撤销")

        def on_key(event):
            if event.keysym == "Escape":
                root.destroy()
            elif event.keysym.lower() == "z" and waypoints:
                waypoints.pop()
                # 重新绘制（简易版：只更新计数）
                status.config(text=f"已撤销，当前 {len(waypoints)} 个途经点")

        canvas.bind("<Button-1>", on_click)
        root.bind("<KeyPress>", on_key)

        root.focus_set()
        root.mainloop()

        return waypoints


# ============================================================
# 路线保存/加载
# ============================================================

def save_route(route: Route, path: str):
    """保存路线到 JSON 文件"""
    import json
    data = {
        "name": route.name,
        "loop": route.loop,
        "waypoints": [
            {"x": w.x, "y": w.y, "label": w.label,
             "walk_key": w.walk_key, "walk_duration": w.walk_duration,
             "mine_duration": w.mine_duration}
            for w in route.waypoints
        ]
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"路线已保存到: {path}")


def load_route(path: str) -> Route:
    """从 JSON 文件加载路线"""
    import json
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    route = Route(name=data.get("name", "路线"), loop=data.get("loop", False))
    for wp_data in data.get("waypoints", []):
        route.waypoints.append(Waypoint(
            x=wp_data["x"], y=wp_data["y"],
            label=wp_data.get("label", ""),
            walk_key=wp_data.get("walk_key", "w"),
            walk_duration=wp_data.get("walk_duration", 2.0),
            mine_duration=wp_data.get("mine_duration", 10.0),
        ))
    return route
