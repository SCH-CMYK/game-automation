import cv2
import numpy as np
import mss
import tkinter as tk
from PIL import Image, ImageTk
import torch
import ssl
import config
import os
import sys
import subprocess
import threading
import time
import ctypes
from ctypes import windll
from pynput import keyboard


# 🌟 导入自定义模块
from tracker_engine import LoftrEngine
from route_manager import RouteManager

ssl._create_default_https_context = ssl._create_unverified_context


def run_selector_if_needed(force=False):
    minimap_cfg = config.settings.get("MINIMAP", {})
    has_valid_config = minimap_cfg and "top" in minimap_cfg and "left" in minimap_cfg

    if not has_valid_config or force:
        print("未检测到有效的小地图坐标，或请求重新校准。")
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
        except Exception:
            sys.exit(1)


# ==========================================
# 🌟 大地图手动选点窗口
# ==========================================
class MapSelectorWindow:
    def __init__(self, root, display_map_bgr, logic_map_shape, callback, close_callback, route_mgr, shared_check_vars):
        self.top = tk.Toplevel(root)
        self.top.title("⚠️ 目标丢失 - 请在大地图上双击定位 (可勾选路线)")
        self.top.attributes("-topmost", True)
        self.top.geometry("1000x800")
        self.top.configure(bg="#2b2b2b")

        self.top.protocol("WM_DELETE_WINDOW", self.on_close)

        self.callback = callback
        self.close_callback = close_callback

        # 🌟 接收主程序的路线管理器和复选框变量，实现状态完全同步
        self.route_mgr = route_mgr
        self.shared_check_vars = shared_check_vars

        self.logic_h, self.logic_w = logic_map_shape
        # 将原始 BGR 图像转换为 RGB 供 Tkinter 显示
        self.full_img_rgb = cv2.cvtColor(display_map_bgr, cv2.COLOR_BGR2RGB)
        self.img_h, self.img_w = self.full_img_rgb.shape[:2]

        # 🌟 独立构建子窗口的顶部菜单和画布
        self.build_ui()

        self.scale = min(1000 / self.img_w, 800 / self.img_h)
        self.offset_x, self.offset_y = 0, 0
        self.start_x, self.start_y = 0, 0

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<MouseWheel>", self.on_scroll)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)

        self.top.update()
        self.center_map()
        self.draw_map()

    def build_ui(self):
        # 1. 顶部操作栏
        self.menu_frame = tk.Frame(self.top, bg="#333333")
        self.menu_frame.pack(side=tk.TOP, fill=tk.X)

        tk.Label(self.menu_frame, text="💡 操作：滚轮缩放 | 左键平移 | 双击确认 | 路线:",
                 bg="#333333", fg="yellow", font=("微软雅黑", 9)).pack(side=tk.LEFT, padx=10)

        # 2. 路线选择下拉菜单
        display_names = {"zhiwu": "🌿 植物", "diquluxian": "📍 路线", "qita": "📦 其他"}
        for cat in self.route_mgr.categories:
            mb = tk.Menubutton(self.menu_frame, text=f" {display_names[cat]} ▼ ", relief=tk.FLAT,
                               bg="#333333", fg="white", activebackground="#444444", font=("微软雅黑", 9))
            mb.pack(side=tk.LEFT, padx=5)

            menu = tk.Menu(mb, tearoff=0, bg="#2b2b2b", fg="white", selectcolor="#00FF00")
            mb["menu"] = menu

            for route in self.route_mgr.route_groups[cat]:
                r_name = route.get("display_name")
                # 🌟 关键：使用主窗口传来的 tk.BooleanVar，这样两边打钩状态自动双向绑定
                var = self.shared_check_vars[r_name]
                menu.add_checkbutton(label=r_name, variable=var, command=lambda n=r_name: self.toggle_route(n))

        # 3. 图像展示画布
        self.canvas = tk.Canvas(self.top, bg="#1e1e1e", cursor="crosshair")
        self.canvas.pack(fill=tk.BOTH, expand=True)

    def on_close(self):
        self.close_callback()
        self.top.destroy()

    def toggle_route(self, name):
        # 更新路线管理器的可见性，并重新画图
        self.route_mgr.visibility[name] = self.shared_check_vars[name].get()
        self.draw_map()

    def center_map(self):
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        self.offset_x = (cw - self.img_w * self.scale) / 2
        self.offset_y = (ch - self.img_h * self.scale) / 2

    def draw_map(self):
        sw, sh = int(self.img_w * self.scale), int(self.img_h * self.scale)
        if sw <= 0 or sh <= 0: return
        img_resized = cv2.resize(self.full_img_rgb, (sw, sh))

        # 🌟 在缩放后的底图上绘制开启的路线
        color_idx = 0
        for cat in self.route_mgr.categories:
            for route in self.route_mgr.route_groups[cat]:
                name = route.get("display_name")
                if not self.route_mgr.visibility.get(name, False):
                    continue

                pts = route.get("points", [])

                # 获取原颜色 (通常是BGR)，因为当前底图换成了RGB格式，所以需要倒序通道
                bgr_color = self.route_mgr.colors[color_idx % len(self.route_mgr.colors)]
                rgb_color = (bgr_color[2], bgr_color[1], bgr_color[0])
                color_idx += 1

                # 将路线的坐标乘以当前的地图缩放比例
                scaled_pts = [(int(p["x"] * self.scale), int(p["y"] * self.scale)) for p in pts]

                # 连线
                for i in range(len(scaled_pts) - 1):
                    cv2.line(img_resized, scaled_pts[i], scaled_pts[i + 1], rgb_color, 2, cv2.LINE_AA)
                if route.get("loop") and len(scaled_pts) > 2:
                    cv2.line(img_resized, scaled_pts[-1], scaled_pts[0], rgb_color, 2, cv2.LINE_AA)

                # 画点 (保持走过的点为黑色，没走过的为红色)
                for sp, p_dict in zip(scaled_pts, pts):
                    # 注意：这是RGB通道图，红色是 (255, 0, 0)，黑色是 (0, 0, 0)
                    pt_color = (0, 0, 0) if p_dict.get("visited", False) else (255, 0, 0)
                    cv2.circle(img_resized, sp, 4, pt_color, -1)

        self.tk_img = ImageTk.PhotoImage(Image.fromarray(img_resized))
        self.canvas.delete("all")
        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.tk_img)

    def on_press(self, event):
        self.start_x, self.start_y = event.x, event.y

    def on_drag(self, event):
        dx, dy = event.x - self.start_x, event.y - self.start_y
        self.offset_x += dx
        self.offset_y += dy
        self.start_x, self.start_y = event.x, event.y
        self.canvas.move("all", dx, dy)

    def on_scroll(self, event):
        f = 1.2 if event.delta > 0 else 0.8
        ns = self.scale * f
        if 0.1 < ns < 10.0:
            mx, my = event.x - self.offset_x, event.y - self.offset_y
            self.offset_x -= mx * (f - 1)
            self.offset_y -= my * (f - 1)
            self.scale = ns
            self.draw_map()

    def on_double_click(self, event):
        ix = (event.x - self.offset_x) / self.scale
        iy = (event.y - self.offset_y) / self.scale
        if 0 <= ix <= self.img_w and 0 <= iy <= self.img_h:
            lx, ly = int(ix / self.img_w * self.logic_w), int(iy / self.img_h * self.logic_h)
            self.top.destroy()
            self.callback(lx, ly)


# ==========================================
# 🌟 主跟点器程序
# ==========================================
class AIMapTrackerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI 雷达 - 鼠标穿透增强版")
        self.root.attributes("-topmost", True)

        # 🌟 设置初始透明度（0.8 表示 80% 不透明）
        self.root.attributes("-alpha", 0.8)

        # 获取初始窗口大小
        self.root.geometry(config.WINDOW_GEOMETRY)

        # --- 1. 基础变量初始化 (必须最先定义) ---
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        print(f"使用设备: {self.device}")

        # 加载地图数据
        self.logic_map_bgr = cv2.imread(config.LOGIC_MAP_PATH)
        self.map_height, self.map_width = self.logic_map_bgr.shape[:2]
        self.display_map_bgr = cv2.imread(config.DISPLAY_MAP_PATH)

        # 状态机与追踪变量
        self.state = "MANUAL_RELOCATE"
        self.last_x, self.last_y = self.map_width // 2, self.map_height // 2
        self.base_search_radius = config.AI_TRACK_RADIUS
        self.current_search_radius = self.base_search_radius
        self.lost_frames, self.max_lost_frames = 0, 4
        self.smoothed_cx, self.smoothed_cy = None, None
        self.selector_open = False
        self.is_running = True
        self.lock = threading.Lock()
        self.latest_display_crop = None

        # 动态视图尺寸变量
        self.view_w = 400
        self.view_h = 400

        # --- 2. 核心模块实例化 ---
        self.engine = LoftrEngine(self.device)
        self.route_mgr = RouteManager("routes")

        # --- 3. UI 构建 ---
        # 顶部菜单栏区域
        self.menu_frame = tk.Frame(self.root, bg="#333333")
        self.menu_frame.pack(side=tk.TOP, fill=tk.X)

        # A. 分类下拉菜单 (基于文件夹)
        display_names = {"zhiwu": "🌿 植物", "diquluxian": "📍 路线", "qita": "📦 其他"}
        self.check_vars = {}
        for cat in self.route_mgr.categories:
            mb = tk.Menubutton(self.menu_frame, text=f" {display_names[cat]} ▼ ", relief=tk.FLAT,
                               bg="#333333", fg="white", activebackground="#444444",
                               activeforeground="#00FF00", font=("微软雅黑", 9))
            mb.pack(side=tk.LEFT, padx=5)

            menu = tk.Menu(mb, tearoff=0, bg="#2b2b2b", fg="white", selectcolor="#00FF00")
            mb["menu"] = menu

            for route in self.route_mgr.route_groups[cat]:
                r_name = route.get("display_name")
                var = tk.BooleanVar(value=False)
                self.check_vars[r_name] = var
                menu.add_checkbutton(label=r_name, variable=var,
                                     command=lambda n=r_name: self.toggle_route(n))

        # B. 透明度调节滑动条
        tk.Label(self.menu_frame, text=" 透明度:", bg="#333333", fg="white", font=("微软雅黑", 9)).pack(side=tk.LEFT,
                                                                                                        padx=5)
        self.alpha_scale = tk.Scale(self.menu_frame, from_=0.1, to=1.0, resolution=0.1,
                                    orient=tk.HORIZONTAL, command=self.update_alpha,
                                    bg="#333333", fg="white", highlightthickness=0,
                                    length=80, showvalue=False)
        self.alpha_scale.set(0.8)
        self.alpha_scale.pack(side=tk.LEFT, padx=5)

        # C. 🌟 锁定穿透开关 (解决鼠标箭头干扰的关键)
        self.lock_var = tk.BooleanVar(value=False)
        self.lock_cb = tk.Checkbutton(self.menu_frame, text="🔒 锁定", variable=self.lock_var,
                                      command=self.toggle_lock,
                                      bg="#333333", fg="orange", selectcolor="#222222",
                                      activebackground="#444444", font=("微软雅黑", 8))
        self.lock_cb.pack(side=tk.LEFT, padx=10)
        self.start_hotkey_listener()

        # D. Canvas 地图展示区
        self.main_frame = tk.Frame(self.root)
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(self.main_frame, bg='#2b2b2b', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.image_on_canvas = None

        # E. 重新选点按钮
        tk.Button(self.main_frame, text="重新选点", command=self.trigger_manual_relocate,
                  bg="#4CAF50", fg="white", font=("微软雅黑", 9, "bold"), relief=tk.FLAT).place(x=5, y=5)

        # --- 4. 事件绑定 ---
        self.root.bind("<Configure>", self.on_window_resize)

        # 只有在非锁定状态下才执行悬停变清晰逻辑
        self.root.bind("<Enter>", self._on_mouse_enter)
        self.root.bind("<Leave>", self._on_mouse_leave)

        # --- 5. 启动任务 ---
        self.minimap_region = config.MINIMAP
        self.ai_thread = threading.Thread(target=self.ai_worker_loop, daemon=True)
        self.ai_thread.start()
        self.ui_render_loop()

    def start_hotkey_listener(self):
        """在独立线程中监听全局热键"""

        def on_press(key):
            # 监听 F9 键
            if key == keyboard.Key.f9:
                # 切换布尔值并触发逻辑
                new_state = not self.lock_var.get()
                self.lock_var.set(new_state)
                self.toggle_lock()  # 核心切换函数

        # 使用守护线程启动，跟随主程序退出
        listener = keyboard.Listener(on_press=on_press)
        listener.daemon = True
        listener.start()

    def toggle_lock(self):
        """核心：设置 Windows 鼠标穿透样式与隐藏边框"""
        import ctypes
        is_locked = self.lock_var.get()

        # 🌟 1. 处理无边框状态 (必须在获取 Windows 句柄前操作)
        if is_locked:
            self.root.overrideredirect(True)  # 隐藏系统标题栏和边框
            # self.menu_frame.pack_forget()   # 💡 可选：连带顶部的菜单栏(透明度、复选框)一起隐藏
        else:
            self.root.overrideredirect(False)  # 恢复系统标题栏和边框
            # self.menu_frame.pack(side=tk.TOP, fill=tk.X, before=self.main_frame) # 💡 可选：如果上面隐藏了菜单栏，这里负责恢复它

        self.root.update_idletasks()  # 强制刷新窗口状态，确保后续获取到的句柄是准确的

        # 🌟 2. 获取窗口句柄并设置穿透
        hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x20
        WS_EX_LAYERED = 0x80000

        # 获取当前样式
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

        if is_locked:
            # 开启穿透：添加透明和层叠样式
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
            self.root.attributes("-alpha", self.alpha_scale.get())  # 保持设定的透明度
            print(">>> [已锁定] 鼠标已穿透，边框已隐藏，按 F9 解锁")
        else:
            # 关闭穿透：移除透明样式
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
            self.root.attributes("-alpha", 1.0)  # 解锁时自动恢复清晰，方便操作
            print(">>> [已解锁] 鼠标恢复交互，边框已恢复")

    def _on_mouse_enter(self, event):
        if not self.lock_var.get():
            self.root.attributes("-alpha", 1.0)

    def _on_mouse_leave(self, event):
        if not self.lock_var.get():
            self.root.attributes("-alpha", self.alpha_scale.get())

    def set_click_through(self, enabled=True):
        """设置窗口是否允许鼠标穿透"""
        # 获取窗口句柄 (HWND)
        hwnd = windll.user32.GetParent(self.root.winfo_id())

        # 定义 Windows 常量
        GWL_EXSTYLE = -20
        WS_EX_LAYERED = 0x80000
        WS_EX_TRANSPARENT = 0x20

        # 获取当前样式
        style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)

        if enabled:
            # 开启穿透：添加透明和层叠样式
            windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED | WS_EX_TRANSPARENT)
            print(">>> 雷达已锁定：鼠标将直接穿透，不再显示箭头")
        else:
            # 关闭穿透：移除透明样式（保留层叠以维持 alpha 透明度）
            windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style & ~WS_EX_TRANSPARENT)
            print(">>> 雷达已解锁：现在可以操作菜单")

    def update_alpha(self, value):
        """同时改变窗口和地图的透明度"""
        # 这个属性会作用于整个窗口，包括地图图片、路线和按钮
        self.root.attributes("-alpha", float(value))

    def toggle_route(self, name):
        """更新路线管理器的可见性状态"""
        new_state = self.check_vars[name].get()
        self.route_mgr.visibility[name] = new_state
        print(f"路线 [{name}] 显示状态修改为: {new_state}")

    def trigger_manual_relocate(self):
        self.selector_open = False  # 强制重置一次标志位，确保能打开
        self.state = "MANUAL_RELOCATE"

        # 🌟 新增：处理选点窗口关闭时的回调
    def reset_selector_flag(self):
        self.selector_open = False
        # 如果用户关闭了选点窗口，把状态改回本地追踪，防止它死循环反复弹出
        if self.state == "MANUAL_RELOCATE":
            self.state = "LOCAL_TRACK"

    def on_relocate_done(self, x, y):
        print(f"📍 重新定位坐标: X={x}, Y={y}")
        self.last_x, self.last_y = x, y
        self.smoothed_cx, self.smoothed_cy = float(x), float(y)
        self.lost_frames = 0
        self.current_search_radius = self.base_search_radius + 200
        self.state = "LOCAL_TRACK"
        self.selector_open = False

    def on_window_resize(self, event):
        """窗口缩放回调"""
        # 仅响应主窗口尺寸变化，过滤掉子组件变化
        if event.widget == self.root:
            self.view_w = self.canvas.winfo_width()
            self.view_h = self.canvas.winfo_height()

    def ai_worker_loop(self):
        """后台 AI 推理线程 - 支持动态窗口缩放"""
        with mss.mss() as sct:
            while self.is_running:
                # 1. 拦截：手动定位模式时降低功耗
                if self.state == "MANUAL_RELOCATE":
                    time.sleep(0.1)
                    continue

                start_time = time.time()

                # 2. 获取当前窗口实时尺寸 (由主线程 Configure 事件更新)
                # 使用局部变量防止计算过程中尺寸突变导致数组越界
                current_vw = self.view_w
                current_vh = self.view_h
                half_vw = current_vw // 2
                half_vh = current_vh // 2

                # 3. 截图小地图
                try:
                    screenshot = sct.grab(self.minimap_region)
                    mini_bgr = np.array(screenshot)[:, :, :3]
                except Exception as e:
                    print(f"截图失败: {e}")
                    time.sleep(0.1)
                    continue

                found = False

                # 4. 确定 AI 搜索区域 (基于逻辑地图)
                x1 = max(0, self.last_x - self.current_search_radius)
                y1 = max(0, self.last_y - self.current_search_radius)
                x2 = min(self.map_width, self.last_x + self.current_search_radius)
                y2 = min(self.map_height, self.last_y + self.current_search_radius)

                local_map = self.logic_map_bgr[y1:y2, x1:x2]

                # 5. 执行 AI 特征匹配
                if local_map.shape[0] >= 16 and local_map.shape[1] >= 16:
                    t_mini = self.engine.preprocess(mini_bgr)
                    t_local = self.engine.preprocess(local_map)

                    corr = self.engine.match(t_mini, t_local)
                    mk0, mk1 = corr['keypoints0'].cpu().numpy(), corr['keypoints1'].cpu().numpy()
                    conf = corr['confidence'].cpu().numpy()

                    v_idx = conf > config.AI_CONFIDENCE_THRESHOLD
                    mk0, mk1 = mk0[v_idx], mk1[v_idx]

                    if len(mk0) >= config.AI_MIN_MATCH_COUNT:
                        M, _ = cv2.findHomography(mk0, mk1, cv2.RANSAC, config.AI_RANSAC_THRESHOLD)
                        if M is not None:
                            h, w = mini_bgr.shape[:2]
                            center = cv2.perspectiveTransform(np.float32([[[w / 2, h / 2]]]), M)
                            rx, ry = center[0][0][0] + x1, center[0][0][1] + y1

                            if 0 <= rx < self.map_width and 0 <= ry < self.map_height:
                                if self.smoothed_cx is None:
                                    self.smoothed_cx, self.smoothed_cy = rx, ry
                                else:
                                    dist = np.sqrt((rx - self.smoothed_cx) ** 2 + (ry - self.smoothed_cy) ** 2)
                                    if dist < 500:  # 允许合理范围内的位置跳变
                                        alpha = 0.15 if dist < 15 else 0.45
                                        self.smoothed_cx = alpha * rx + (1 - alpha) * self.smoothed_cx
                                        self.smoothed_cy = alpha * ry + (1 - alpha) * self.smoothed_cy
                                        found = True

                # 6. 状态维护
                if found:
                    self.last_x, self.last_y = int(self.smoothed_cx), int(self.smoothed_cy)
                    self.lost_frames, self.current_search_radius = 0, self.base_search_radius
                else:
                    self.lost_frames += 1
                    if self.lost_frames == 1:
                        self.current_search_radius += 300  # 丢失首帧扩大搜索圈
                    if self.lost_frames > self.max_lost_frames:
                        self.state = "MANUAL_RELOCATE"

                # 7. 动态渲染裁剪 (核心修改：使用窗口实时宽高)
                vx1, vy1 = max(0, self.last_x - half_vw), max(0, self.last_y - half_vh)
                vx2, vy2 = min(self.map_width, self.last_x + half_vw), min(self.map_height, self.last_y + half_vh)

                # 裁剪展示用大地图
                crop = self.display_map_bgr[vy1:vy2, vx1:vx2].copy()

                # 8. 绘制路线 (传递动态窗口尺寸以适配绘制逻辑)
                # 这里假设 RouteManager.draw_on 的最后一个参数改为最大边长或自适应
                # 传入 self.last_x 和 self.last_y 作为人物当前位置
                self.route_mgr.draw_on(crop, vx1, vy1, max(current_vw, current_vh), self.last_x, self.last_y)

                # 9. 绘制玩家箭头 (原生小地图箭头抠图)
                mh, mw = mini_bgr.shape[:2]
                asize = 12
                # 提取小地图中心的箭头
                arrow = mini_bgr[mh // 2 - asize: mh // 2 + asize, mw // 2 - asize: mw // 2 + asize].copy()

                # 计算箭头在 crop 上的局部坐标
                ay_local, ax_local = self.last_y - vy1 - asize, self.last_x - vx1 - asize

                # 检查边界防止绘制越界
                if 0 <= ay_local < crop.shape[0] - 2 * asize and 0 <= ax_local < crop.shape[1] - 2 * asize:
                    roi = crop[ay_local: ay_local + 2 * asize, ax_local: ax_local + 2 * asize]
                    # 透明度融合
                    crop[ay_local: ay_local + 2 * asize, ax_local: ax_local + 2 * asize] = \
                        cv2.addWeighted(arrow, 0.8, roi, 0.2, 0)

                # 10. 放入共享变量供主线程 Canvas 渲染
                with self.lock:
                    self.latest_display_crop = crop

                # 频率控制
                st = max(0, (config.AI_REFRESH_RATE / 1000.0) - (time.time() - start_time))
                time.sleep(st)

    def ui_render_loop(self):
        """主线程渲染循环 - 支持动态窗口缩放"""
        # 获取当前画布的实时尺寸
        current_vw = self.view_w
        current_vh = self.view_h

        if self.state == "MANUAL_RELOCATE":
            if not self.selector_open:
                self.selector_open = True
                torch.cuda.empty_cache()
                MapSelectorWindow(
                    self.root,
                    self.display_map_bgr,
                    (self.map_height, self.map_width),
                    self.on_relocate_done,
                    self.reset_selector_flag,
                    self.route_mgr,  # 🌟 传路线管理器
                    self.check_vars  # 🌟 传多选框状态，实现内外同步
                )

            # 🌟 修改：创建一个匹配当前窗口尺寸的黑色背景提示图
            # 防止视图尺寸为0时报错
            draw_w = max(current_vw, 100)
            draw_h = max(current_vh, 100)

            blank = np.zeros((draw_h, draw_w, 3), np.uint8)

            # 将提示文字居中显示
            text = "Waiting for Relocation..."
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2
            text_size = cv2.getTextSize(text, font, font_scale, thickness)[0]
            text_x = (draw_w - text_size[0]) // 2
            text_y = (draw_h + text_size[1]) // 2

            cv2.putText(blank, text, (text_x, text_y), font, font_scale, (0, 165, 255), thickness)
            self._render_to_canvas(blank)

        else:
            # 正常追踪状态
            with self.lock:
                if self.latest_display_crop is not None:
                    # 直接渲染 AI 线程根据窗口尺寸裁剪好的画面
                    self._render_to_canvas(self.latest_display_crop)

        # 保持约 33 FPS 的刷新率
        self.root.after(30, self.ui_render_loop)

    def _render_to_canvas(self, crop):
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        self.tk_image = ImageTk.PhotoImage(Image.fromarray(rgb))
        if self.image_on_canvas is None:
            self.image_on_canvas = self.canvas.create_image(0, 0, anchor=tk.NW, image=self.tk_image)
        else:
            self.canvas.itemconfig(self.image_on_canvas, image=self.tk_image)


if __name__ == "__main__":
    run_selector_if_needed(force=True)
    root = tk.Tk()
    app = AIMapTrackerApp(root)
    root.mainloop()