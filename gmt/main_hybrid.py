import cv2
import numpy as np
import mss
import tkinter as tk
from PIL import Image, ImageTk
import torch
import torch.nn as nn
from torchvision.models import resnet50
from torchvision.models import mobilenet_v3_small
from torchvision.models import resnet18, ResNet18_Weights
from torchvision import transforms
import time
import os
import sys
import subprocess
import config


# ==========================================
# 1. 小地图校准器逻辑
# ==========================================
def run_selector_if_needed(force=False):
    minimap_cfg = config.settings.get("MINIMAP", {})
    has_valid_config = minimap_cfg and "top" in minimap_cfg and "left" in minimap_cfg

    if not has_valid_config or force:
        print(">>> 正在启动小地图选择器...")
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
            selector_path = os.path.join(base_dir, "MinimapSetup.exe")
            command = [selector_path]
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            selector_path = os.path.join(base_dir, "selector.py")
            command = [sys.executable, selector_path]
        try:
            subprocess.run(command, check=True)
            import importlib
            importlib.reload(config)
        except Exception as e:
            print(f"⚠️ 选择器异常: {e}")
            sys.exit(1)


# ==========================================
# 2. ResNet-50 热力图神经网络结构
# ==========================================
# class MapTrackerNet(nn.Module):
#     def __init__(self, heatmap_size=64):
#         super().__init__()
#         self.heatmap_size = heatmap_size
#
#         self.backbone = resnet50(weights=None)
#         in_features = self.backbone.fc.in_features
#
#         self.backbone.fc = nn.Sequential(
#             nn.Linear(in_features, heatmap_size * heatmap_size),
#             nn.Sigmoid()
#         )
#
#     def forward(self, x):
#         x = self.backbone(x)
#         return x.view(-1, 1, self.heatmap_size, self.heatmap_size)
# class HeatmapTrackerNet(nn.Module):
#     def __init__(self, heatmap_size=64):
#         super().__init__()
#         self.heatmap_size = heatmap_size
#
#         # 加载带预训练权重的轻量化骨干网络 (参数量仅 250 万)
#         self.backbone = mobilenet_v3_small(weights=None)
#
#         # 获取 MobileNetV3 分类器的输入特征维度 (通常是 576)
#         in_features = self.backbone.classifier[0].in_features
#
#         # 🌟 核心改动：彻底覆盖原本的 classifier，输出 4096 个节点并加上 Sigmoid
#         self.backbone.classifier = nn.Sequential(
#             nn.Linear(in_features, self.heatmap_size * self.heatmap_size),
#             nn.Sigmoid()
#         )
#
#     def forward(self, x):
#         x = self.backbone(x)
#         # 将扁平的 4096 向量，重新折叠成 (Batch_size, 1通道, 64高度, 64宽度) 的热力图
#         return x.view(-1, 1, self.heatmap_size, self.heatmap_size)
# ==========================================
# 2. 定义中量级神经网络 (ResNet18 热力图版)
# ==========================================
class HeatmapTrackerNet(nn.Module):
    def __init__(self, heatmap_size=64):
        super().__init__()
        self.heatmap_size = heatmap_size

        # 加载 ResNet18 骨干网络 (参数量约 1100 万，性能与速度的完美平衡)
        self.backbone = resnet18(weights=None)

        # 获取 ResNet18 全连接层的输入特征维度 (512)
        in_features = self.backbone.fc.in_features

        # 彻底覆盖原本的 fc 层，输出 4096 个节点并加上 Sigmoid
        self.backbone.fc = nn.Sequential(
            nn.Linear(in_features, self.heatmap_size * self.heatmap_size),
            nn.Sigmoid()
        )

    def forward(self, x):
        x = self.backbone(x)
        # 将扁平的 4096 向量，重新折叠成 (Batch_size, 1通道, 64高度, 64宽度) 的热力图
        return x.view(-1, 1, self.heatmap_size, self.heatmap_size)

# ==========================================
# 3. 混合跟点主程序 (AI热力图导盲 + 局部SIFT精修)
# ==========================================
class HybridSiftTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI热力图+SIFT 终极混合跟点")

        self.root.attributes("-topmost", True)
        self.root.geometry(config.WINDOW_GEOMETRY)

        # --- 1. 加载双地图 ---
        print(f"正在加载逻辑大地图 ({config.LOGIC_MAP_PATH})...")
        self.logic_map_bgr = cv2.imread(config.LOGIC_MAP_PATH)
        self.map_height, self.map_width = self.logic_map_bgr.shape[:2]
        self.logic_map_gray = cv2.cvtColor(self.logic_map_bgr, cv2.COLOR_BGR2GRAY)

        print(f"正在加载显示大地图 ({config.DISPLAY_MAP_PATH})...")
        self.display_map_bgr = cv2.imread(config.DISPLAY_MAP_PATH)

        # --- 2. 加载 ResNet-50 热力图模型 ---
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = HeatmapTrackerNet(heatmap_size=64).to(self.device)
        model_path = "best_tracker_model.pth"
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"找不到模型文件：{model_path}。请确认已完成 ResNet-50 热力图训练！")

        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model.eval()
        print(f"✅ AI 热力图引擎加载成功 ({self.device})")

        self.transform = transforms.Compose([
            transforms.ToTensor(),
            transforms.Resize((150, 150), antialias=True),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        # --- 3. 初始化 SIFT 引擎 ---
        self.sift = cv2.SIFT_create()
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        self.flann = cv2.FlannBasedMatcher(index_params, search_params)

        # 【修改 1 - 增强特征】：将 clipLimit 从 2.0 提高到 3.0，
        # 这会极大增强局部图像的对比度，让模糊的地形也能被 SIFT 抠出特征点！
        self.clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))

        # --- 4. 截图与 UI ---
        self.sct = mss.mss()
        self.minimap_region = config.MINIMAP
        self.canvas = tk.Canvas(root, width=config.VIEW_SIZE, height=config.VIEW_SIZE, bg='#2b2b2b')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.image_on_canvas = None

        # 【修改 2 - 降低范围】：因为 AI 已经很准了，将 SIFT 的二次搜索半径从 250 骤降到 100！
        # 面积缩小了 6 倍，SIFT 的计算速度将发生质的飞跃，且能有效防止匹配到远处的相似地形。
        self.sift_radius = 100
        self.update_tracker()

    def update_tracker(self):
        start_time = time.time()

        # 1. 抓取截图
        screenshot = self.sct.grab(self.minimap_region)
        minimap_bgr = np.array(screenshot)[:, :, :3]

        # 🌟 终极物理外挂：甜甜圈遮罩的统一生成
        h, w = minimap_bgr.shape[:2]
        cx, cy = w // 2, h // 2
        donut_mask = np.zeros((h, w), dtype=np.uint8)

        outer_radius = min(w, h) // 2
        inner_radius = 15

        cv2.circle(donut_mask, (cx, cy), outer_radius, 255, -1)
        cv2.circle(donut_mask, (cx, cy), inner_radius, 0, -1)

        # ==========================================
        # 阶段一：AI 热力图粗定位
        # ==========================================
        # 给 AI 喂干净的甜甜圈
        minimap_rgb = cv2.cvtColor(minimap_bgr, cv2.COLOR_BGR2RGB)
        minimap_rgb = cv2.bitwise_and(minimap_rgb, minimap_rgb, mask=donut_mask)

        input_tensor = self.transform(minimap_rgb).unsqueeze(0).to(self.device)

        with torch.no_grad():
            output_heatmap = self.model(input_tensor)

        heatmap = output_heatmap[0, 0].cpu().numpy()
        y_idx, x_idx = np.unravel_index(np.argmax(heatmap), heatmap.shape)

        heatmap_size = float(self.model.heatmap_size)
        norm_x = x_idx / heatmap_size
        norm_y = y_idx / heatmap_size

        ai_cx = int(norm_x * self.map_width)
        ai_cy = int(norm_y * self.map_height)

        # ==========================================
        # 阶段二：局部极速 SIFT 精修
        # ==========================================
        # 【核心修正】：让 SIFT 也只看甜甜圈区域！彻底断绝 SIFT 被 UI 图标干扰的可能性
        minimap_gray = cv2.cvtColor(minimap_bgr, cv2.COLOR_BGR2GRAY)
        minimap_gray = cv2.bitwise_and(minimap_gray, minimap_gray, mask=donut_mask)
        minimap_gray = self.clahe.apply(minimap_gray)  # 应用增强过的对比度

        # 裁剪大地图上的局部大区
        x1 = max(0, ai_cx - self.sift_radius)
        y1 = max(0, ai_cy - self.sift_radius)
        x2 = min(self.map_width, ai_cx + self.sift_radius)
        y2 = min(self.map_height, ai_cy + self.sift_radius)

        local_area_gray = self.logic_map_gray[y1:y2, x1:x2].copy()
        local_area_gray = self.clahe.apply(local_area_gray)

        kp_mini, des_mini = self.sift.detectAndCompute(minimap_gray, None)
        kp_local, des_local = self.sift.detectAndCompute(local_area_gray, None)

        found = False
        final_cx, final_cy = ai_cx, ai_cy  # 默认使用 AI 坐标
        match_count = 0

        if des_mini is not None and des_local is not None and len(kp_mini) >= 2:
            matches = self.flann.knnMatch(des_mini, des_local, k=2)

            # 【修改 3 - 降低门槛】：Lowe's ratio 从 0.7 放宽到 0.8
            # 允许更多“长得稍微有点像”的特征点被保留下来
            good_matches = [m for m, n in matches if m.distance < 0.9 * n.distance]
            match_count = len(good_matches)

            # 【修改 4 - 降低门槛】：最低匹配点数从 10 降到 6
            # 在 100x100 的极小搜索范围里，6 个点足够锁定位置了
            if match_count >= 8:
                src_pts = np.float32([kp_mini[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                dst_pts = np.float32([kp_local[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

                # 【修改 5 - 增强容错】：RANSAC 容差从 5.0 放宽到 8.0
                # 容许小地图在旋转和拉伸时存在更大的形变误差
                M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

                if M is not None:
                    h, w = minimap_gray.shape
                    center_pt = np.float32([[[w / 2, h / 2]]])
                    dst_center_local = cv2.perspectiveTransform(center_pt, M)

                    final_cx = int(dst_center_local[0][0][0]) + x1
                    final_cy = int(dst_center_local[0][0][1]) + y1
                    found = True

        # ==========================================
        # UI 渲染
        # ==========================================
        half_view = config.VIEW_SIZE // 2
        vy1 = max(0, final_cy - half_view)
        vy2 = min(self.map_height, final_cy + half_view)
        vx1 = max(0, final_cx - half_view)
        vx2 = min(self.map_width, final_cx + half_view)

        display_crop = self.display_map_bgr[vy1:vy2, vx1:vx2].copy()
        local_x, local_y = final_cx - vx1, final_cy - vy1

        if found:
            cv2.circle(display_crop, (local_x, local_y), 10, (0, 0, 255), -1)
            cv2.circle(display_crop, (local_x, local_y), 12, (255, 255, 255), 2)
            cv2.putText(display_crop, f"SIFT Precise ({match_count})", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.circle(display_crop, (local_x, local_y), 10, (0, 255, 255), -1)
            cv2.putText(display_crop, "AI Heatmap Coarse", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 165, 255), 2)

        cost = (time.time() - start_time) * 1000
        cv2.putText(display_crop, f"{cost:.1f} ms", (10, config.VIEW_SIZE - 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        display_rgb = cv2.cvtColor(display_crop, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(display_rgb)
        final_img = Image.new('RGB', (config.VIEW_SIZE, config.VIEW_SIZE), (43, 43, 43))
        final_img.paste(pil_img, (max(0, half_view - pil_img.width // 2), max(0, half_view - pil_img.height // 2)))

        self.tk_image = ImageTk.PhotoImage(final_img)
        if self.image_on_canvas is None:
            self.image_on_canvas = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        else:
            self.canvas.itemconfig(self.image_on_canvas, image=self.tk_image)

        self.root.after(30, self.update_tracker)


if __name__ == "__main__":
    run_selector_if_needed(force=True)
    root = tk.Tk()
    app = HybridSiftTrackerApp(root)
    root.mainloop()