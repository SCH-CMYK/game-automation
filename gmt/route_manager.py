import json
import glob
import os
import cv2
import math

class RouteManager:
    def __init__(self, base_folder="routes"):
        self.base_folder = base_folder
        self.categories = ["zhiwu", "diquluxian", "qita"]
        self.route_groups = {cat: [] for cat in self.categories}
        self.visibility = {}
        self._load_all_routes()
        self.colors = [(0, 255, 0), (255, 165, 0), (0, 255, 255), (255, 0, 255), (0, 128, 255)]

    def draw_on(self, canvas, vx1, vy1, view_size, player_x=None, player_y=None):
        color_idx = 0

        # 计算人物在当前裁剪画布 (canvas) 上的局部坐标
        local_player_pt = None
        if player_x is not None and player_y is not None:
            local_player_pt = (int(player_x - vx1), int(player_y - vy1))

        close_threshold = 20  # 🌟 靠近判定距离

        for cat in self.categories:
            for route in self.route_groups[cat]:
                name = route.get("display_name")
                if not self.visibility.get(name, False):
                    continue

                pts = route.get("points", [])
                color = self.colors[color_idx % len(self.colors)]
                color_idx += 1

                # 生成局部坐标
                local_pts = [(int(p["x"] - vx1), int(p["y"] - vy1)) for p in pts]

                # 画线
                for i in range(len(local_pts) - 1):
                    cv2.line(canvas, local_pts[i], local_pts[i + 1], color, 2, cv2.LINE_AA)

                if route.get("loop") and len(local_pts) > 2:
                    cv2.line(canvas, local_pts[-1], local_pts[0], color, 2, cv2.LINE_AA)

                # 🌟 画点：使用 zip 将局部坐标(lp)和原始数据字典(p_dict)绑定循环
                for lp, p_dict in zip(local_pts, pts):
                    if 0 <= lp[0] <= view_size and 0 <= lp[1] <= view_size:
                        pt_radius = 5

                        # 1. 如果这个点已经被踩过，直接标黑
                        if p_dict.get("visited", False):
                            pt_color = (0, 0, 0)
                        else:
                            # 2. 如果没被踩过，判断现在是否靠近
                            pt_color = (0, 0, 255)  # 默认红色
                            if local_player_pt:
                                dist = math.hypot(lp[0] - local_player_pt[0], lp[1] - local_player_pt[1])
                                if dist < close_threshold:
                                    p_dict["visited"] = True  # 🌟 核心：打上永久标记
                                    pt_color = (0, 0, 0)  # 标为黑色

                        # 绘制实心圆
                        cv2.circle(canvas, lp, pt_radius, pt_color, -1)

    def _load_all_routes(self):
        for cat in self.categories:
            cat_path = os.path.join(self.base_folder, cat)
            if not os.path.exists(cat_path):
                os.makedirs(cat_path)
                continue

            for path in glob.glob(os.path.join(cat_path, "*.json")):
                try:
                    # 🌟 核心修改：获取文件名（不带后缀）作为路线名
                    file_name = os.path.basename(path)
                    route_name = os.path.splitext(file_name)[0]

                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        # 将文件名强制写入数据字典，方便后续调用
                        data["display_name"] = route_name

                        self.route_groups[cat].append(data)
                        self.visibility[route_name] = False
                except Exception as e:
                    print(f"加载失败 {path}: {e}")
