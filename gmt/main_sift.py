import cv2
import numpy as np
import mss
import tkinter as tk
from PIL import Image, ImageTk
import time
import config  # <--- 导入同目录下的配置文件
import subprocess
import os
import sys

def run_selector_if_needed(force=False):
    """
    检查是否需要运行小地图校准工具。
    :param force: 如果为 True，无视配置强制重新校准
    """
    # 检查 config.json 中是否已经有了合法的坐标
    minimap_cfg = config.settings.get("MINIMAP", {})
    has_valid_config = minimap_cfg and "top" in minimap_cfg and "left" in minimap_cfg

    if not has_valid_config or force:
        print("未检测到有效的小地图坐标，或请求重新校准。")
        print(">>> 正在启动小地图选择器...")

        # 兼容打包后的 .exe 运行路径
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
            selector_path = os.path.join(base_dir, "MinimapSetup.exe")  # 假设你把 selector 打包成了这个名字
            command = [selector_path]
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            selector_path = os.path.join(base_dir, "selector.py")
            command = [sys.executable, selector_path]

        try:
            # 阻塞运行：等待 selector 窗口关闭后，才会继续执行下面的代码
            subprocess.run(command, check=True)
            print("<<< 选择器关闭，坐标已更新！")

            # 重要：因为配置文件被 selector 修改了，我们需要重新加载一次 config 模块的数据
            import importlib
            importlib.reload(config)

        except FileNotFoundError:
            print(f"❌ 严重错误：找不到小地图选择器工具！期望路径：{selector_path}")
            print("请手动修改 config.json 或确保选择器工具存在。")
            sys.exit(1)  # 如果连选择器都没有，且没有配置，只能退出程序
        except subprocess.CalledProcessError:
            print("⚠️ 选择器异常退出，可能未保存坐标。")

class SiftMapTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SIFT 双地图跟点 (逻辑与显示分离)")

        # --- 1. 窗口属性设置 ---
        self.root.attributes("-topmost", True)
        # --- 使用配置文件中的悬浮窗几何设置 ---
        self.root.geometry(config.WINDOW_GEOMETRY)

        # --- 2. 状态记忆初始化 (惯性导航兜底) ---
        self.last_x = None
        self.last_y = None
        self.lost_frames = 0
        # --- 使用配置文件中的最大丢失帧数 ---
        self.MAX_LOST_FRAMES = config.MAX_LOST_FRAMES

        # --- 3. 加载【逻辑地图】(用于特征匹配，必须是纯净底图) ---
        print(f"正在加载逻辑大地图 ({config.LOGIC_MAP_PATH})，请稍候...")
        self.logic_map_bgr = cv2.imread(config.LOGIC_MAP_PATH)
        if self.logic_map_bgr is None:
            raise FileNotFoundError(f"找不到逻辑地图文件: {config.LOGIC_MAP_PATH}，请检查路径！")
        self.map_height, self.map_width = self.logic_map_bgr.shape[:2]

        logic_map_gray = cv2.cvtColor(self.logic_map_bgr, cv2.COLOR_BGR2GRAY)

        # --- 4. 加载【显示地图】(用于UI渲染，带各种标记点) ---
        print(f"正在加载显示大地图 ({config.DISPLAY_MAP_PATH})，请稍候...")
        self.display_map_bgr = cv2.imread(config.DISPLAY_MAP_PATH)
        if self.display_map_bgr is None:
            raise FileNotFoundError(f"找不到显示地图文件: {config.DISPLAY_MAP_PATH}，请检查路径！")

        # 严格检查两张地图尺寸是否一致！
        dh, dw = self.display_map_bgr.shape[:2]
        if dh != self.map_height or dw != self.map_width:
            raise ValueError(
                f"严重错误：逻辑地图({self.map_width}x{self.map_height}) 与 显示地图({dw}x{dh}) 尺寸不一致！")

        # --- 5. 初始化 CLAHE (极度增强对比度) ---
        # --- 使用配置文件中的 CLAHE 增强极限 ---
        self.clahe = cv2.createCLAHE(clipLimit=config.SIFT_CLAHE_LIMIT, tileGridSize=(8, 8))
        print("正在对逻辑地图进行 CLAHE 纹理增强...")
        # 注意：只对逻辑地图进行特征增强，显示地图保持原样不动！
        logic_map_gray = self.clahe.apply(logic_map_gray)

        # --- 6. 初始化 SIFT 算法 ---
        print("正在提取逻辑地图的全局特征点 (可能需要 5~15 秒，只运行一次)...")
        self.sift = cv2.SIFT_create()
        # 注意：特征提取也是在逻辑图上做的！
        self.kp_big, self.des_big = self.sift.detectAndCompute(logic_map_gray, None)
        print(f"✅ 大地图特征初始化完成！共找到 {len(self.kp_big)} 个锚点。")

        # --- 7. 配置 FLANN 匹配器 ---
        FLANN_INDEX_KDTREE = 1
        index_params = dict(algorithm=FLANN_INDEX_KDTREE, trees=5)
        search_params = dict(checks=50)
        self.flann = cv2.FlannBasedMatcher(index_params, search_params)

        # --- 8. 屏幕截图设置 (MSS) ---
        self.sct = mss.mss()
        # --- 使用配置文件中的截图区域 ---
        self.minimap_region = config.MINIMAP

        # --- 9. UI 组件 ---
        # --- 使用配置文件中的悬浮窗视野大小 (VIEW_SIZE) ---
        self.canvas = tk.Canvas(root, width=config.VIEW_SIZE, height=config.VIEW_SIZE, bg='#2b2b2b')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.image_on_canvas = None

        self.update_tracker()

    def update_tracker(self):
        # 1. 截屏
        screenshot = self.sct.grab(self.minimap_region)
        minimap_bgr = np.array(screenshot)[:, :, :3]
        minimap_gray = cv2.cvtColor(minimap_bgr, cv2.COLOR_BGR2GRAY)

        # 应用 CLAHE 增强小地图
        minimap_gray = self.clahe.apply(minimap_gray)

        # 2. 提取当前小地图的 SIFT 特征
        kp_mini, des_mini = self.sift.detectAndCompute(minimap_gray, None)

        found = False
        center_x, center_y = None, None
        is_inertial = False  # 标记是否处于惯性导航状态

        if des_mini is not None and len(kp_mini) >= 2:
            matches = self.flann.knnMatch(des_mini, self.des_big, k=2)

            good_matches = []
            for m_n in matches:
                if len(m_n) == 2:
                    m, n = m_n
                    # --- 使用配置文件中的 Lowe's Ratio 阈值 ---
                    if m.distance < config.SIFT_MATCH_RATIO * n.distance:
                        good_matches.append(m)

            # --- 使用配置文件中的最低匹配点数 ---
            if len(good_matches) >= config.SIFT_MIN_MATCH_COUNT:
                src_pts = np.float32([kp_mini[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                dst_pts = np.float32([self.kp_big[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

                # --- 使用配置文件中的 RANSAC 误差阈值 ---
                M, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, config.SIFT_RANSAC_THRESHOLD)

                if M is not None:
                    h, w = minimap_gray.shape
                    center_pt = np.float32([[[w / 2, h / 2]]])

                    # 算出坐标
                    dst_center = cv2.perspectiveTransform(center_pt, M)
                    temp_x = int(dst_center[0][0][0])
                    temp_y = int(dst_center[0][0][1])

                    if 0 <= temp_x < self.map_width and 0 <= temp_y < self.map_height:
                        found = True
                        center_x = temp_x
                        center_y = temp_y

                        self.last_x = center_x
                        self.last_y = center_y
                        self.lost_frames = 0

        # --- 惯性兜底 ---
        if not found and self.last_x is not None:
            self.lost_frames += 1
            if self.lost_frames <= self.MAX_LOST_FRAMES:
                found = True
                center_x = self.last_x
                center_y = self.last_y
                is_inertial = True

        # --- 【速度起飞的核心：局部裁剪与渲染】 ---
        # 提取视野半径，方便动态调整大小
        half_view = config.VIEW_SIZE // 2

        if found:
            # --- 使用配置文件计算裁剪边界 ---
            y1 = max(0, center_y - half_view)
            y2 = min(self.map_height, center_y + half_view)
            x1 = max(0, center_x - half_view)
            x2 = min(self.map_width, center_x + half_view)

            # 只复制我们需要显示的区域，内存开销几乎为 0！
            display_crop = self.display_map_bgr[y1:y2, x1:x2].copy()

            # 将大地图上的绝对坐标 (center_x, center_y) 转换为小图上的相对坐标
            local_x = center_x - x1
            local_y = center_y - y1

            if not is_inertial:
                # 画玩家红点 (精确锁定)
                cv2.circle(display_crop, (local_x, local_y), radius=10, color=(0, 0, 255), thickness=-1)
                cv2.circle(display_crop, (local_x, local_y), radius=12, color=(255, 255, 255), thickness=2)
            else:
                # 画黄点推测 (惯性)
                cv2.circle(display_crop, (local_x, local_y), radius=10, color=(0, 255, 255), thickness=-1)
                cv2.circle(display_crop, (local_x, local_y), radius=12, color=(0, 150, 150), thickness=2)

        else:
            # --- 使用配置文件生成未找到时的黑色背景板 ---
            display_crop = np.zeros((config.VIEW_SIZE, config.VIEW_SIZE, 3), dtype=np.uint8)
            cv2.putText(display_crop, "SIFT Searching...", (70, 200), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        display_rgb = cv2.cvtColor(display_crop, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(display_rgb)

        # --- 使用配置文件生成底板并居中粘贴 ---
        final_img = Image.new('RGB', (config.VIEW_SIZE, config.VIEW_SIZE), (43, 43, 43))
        final_img.paste(pil_image,
                        (max(0, half_view - pil_image.width // 2), max(0, half_view - pil_image.height // 2)))

        self.tk_image = ImageTk.PhotoImage(final_img)

        if self.image_on_canvas is None:
            self.image_on_canvas = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        else:
            self.canvas.itemconfig(self.image_on_canvas, image=self.tk_image)

        # --- 使用配置文件中的刷新频率 ---
        self.root.after(config.SIFT_REFRESH_RATE, self.update_tracker)


if __name__ == "__main__":
    run_selector_if_needed(force=True)
    root = tk.Tk()
    app = SiftMapTrackerApp(root)
    root.mainloop()