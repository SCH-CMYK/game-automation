"""
GameAuto — YOLO + YOLOE 双模自动化（检测 + 训练 + 路线规划）
"""
import os, sys, time, threading, math
from pathlib import Path
from datetime import datetime
import random

import cv2, numpy as np
from PIL import Image, ImageTk
import customtkinter as ctk
from tkinter import messagebox, filedialog

sys.path.insert(0, str(Path(__file__).parent))

import logging
from src.utils.logger import get_logger, install_crash_handler

# 初始化日志系统
logger = get_logger("gameauto.main")
install_crash_handler()

# 检查分辨率变更
from src.utils.config import check_resolution_change
check_resolution_change()

from src.engine.screen_capture import ScreenCapture
from src.engine.vision_engine import VisionEngine
from src.engine.controller import Controller
from src.automation.automator import Automator
from src.automation.hotkey import create_hotkey

logger = logging.getLogger("gameauto.main")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")
PROJECT_DIR = Path(__file__).parent.resolve()
HAS_CUDA = __import__('torch').cuda.is_available()


class GameAuto(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("GameAuto — AI 游戏助手")
        self.geometry("1200x750")
        self.minsize(900, 600)

        self.capture = ScreenCapture()
        self.vision = VisionEngine()
        self.controller = Controller()
        self.automator = Automator(self.capture, self.vision, self.controller)

        self.target_class = "ore"
        self.preview_active = False
        self._preview_frame = None
        self._fps_times = []

        self._build_sidebar()
        self._build_tabs()
        self._setup_hotkeys()
        self._refresh_models()
        self._start_preview()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ========== 侧边栏 ==========
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, width=280, corner_radius=0)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        ctk.CTkLabel(sb, text="GameAuto", font=ctk.CTkFont(size=22, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(sb, text="单一多类模型", font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(0, 12))

        # 模型加载
        f = ctk.CTkFrame(sb); f.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(f, text="多类模型", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=8, pady=(8, 2))
        ctk.CTkLabel(f, text="含 ore/creature/obstacle/character",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w", padx=8)
        self.model_combo = ctk.CTkComboBox(f, values=[], width=240)
        self.model_combo.pack(fill="x", padx=8, pady=2)
        r = ctk.CTkFrame(f, fg_color="transparent"); r.pack(fill="x", padx=8, pady=(2, 8))
        ctk.CTkButton(r, text="加载模型", command=self._load_model, height=28).pack(side="left", fill="x", expand=True, padx=(0, 3))
        ctk.CTkButton(r, text="刷新", command=self._refresh_models, width=50, height=28).pack(side="left")

        # 采矿
        f = ctk.CTkFrame(sb); f.pack(fill="x", padx=12, pady=(0, 6))
        ctk.CTkLabel(f, text="自动采矿", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=8, pady=(8, 2))
        r = ctk.CTkFrame(f, fg_color="transparent"); r.pack(fill="x", padx=8, pady=(2, 4))
        self.start_btn = ctk.CTkButton(r, text="开始", command=self._start_mining, fg_color="#2E7D32")
        self.start_btn.pack(side="left", fill="x", expand=True, padx=(0, 3))
        self.pause_btn = ctk.CTkButton(r, text="暂停", command=self._pause_mining, state="disabled")
        self.pause_btn.pack(side="left", fill="x", expand=True, padx=(3, 0))
        self.stop_btn = ctk.CTkButton(f, text="停止", command=self._stop_mining, fg_color="#C62828", height=28)
        self.stop_btn.pack(fill="x", padx=8, pady=(0, 4))
        self.stats_label = ctk.CTkLabel(f, text="待开始", font=ctk.CTkFont(size=11))
        self.stats_label.pack(anchor="w", padx=8, pady=(0, 8))

        # 局内热键（大块显示）
        f = ctk.CTkFrame(sb); f.pack(fill="x", padx=12, pady=(6, 20))
        ctk.CTkLabel(f, text="快捷键（游戏内可用）",
                     font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", padx=10, pady=(8, 4))
        hotkeys = [
            ("Ctrl+T", "计时截图"),
            ("Ctrl+L", "单张截图"),
            ("Ctrl+Shift+Q", "紧急停止"),
        ]
        for key, desc in hotkeys:
            r = ctk.CTkFrame(f, fg_color="transparent")
            r.pack(fill="x", padx=10, pady=1)
            ctk.CTkLabel(r, text=key, font=ctk.CTkFont(size=12, family="Consolas"),
                         text_color="#64B5F6", width=160, anchor="w").pack(side="left")
            ctk.CTkLabel(r, text=desc, font=ctk.CTkFont(size=12),
                         text_color="gray").pack(side="left")
        # 计时截图间隔
        r = ctk.CTkFrame(f, fg_color="transparent"); r.pack(fill="x", padx=10, pady=(2, 0))
        ctk.CTkLabel(r, text="计时间隔(秒):", font=ctk.CTkFont(size=11)).pack(side="left")
        self.auto_ss_interval_var = ctk.StringVar(value="2.0")
        ctk.CTkEntry(r, textvariable=self.auto_ss_interval_var, width=50, height=22).pack(side="left", padx=(4, 0))

        ctk.CTkLabel(f, text="需以管理员运行", font=ctk.CTkFont(size=10),
                     text_color="#FF8A65").pack(anchor="w", padx=10, pady=(2, 8))

    # ========== 主区域 Tabs ==========
    def _build_tabs(self):
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(side="right", fill="both", expand=True, padx=10, pady=10)

        self.tab_preview = self.tabview.add("检测预览")
        self.tab_train = self.tabview.add("模型训练")
        self.tab_route = self.tabview.add("路线规划")

        self._build_preview_tab()
        self._build_train_tab()
        self._build_route_tab()

    def _build_preview_tab(self):
        tab = self.tab_preview
        self.canvas = ctk.CTkCanvas(tab, bg="#1a1a1a", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)

        bar = ctk.CTkFrame(tab, height=28, fg_color="transparent")
        bar.pack(fill="x")
        self.status_var = ctk.StringVar(value="就绪 — 加载模型后开始")
        ctk.CTkLabel(bar, textvariable=self.status_var, font=ctk.CTkFont(size=11)).pack(side="left", padx=8)
        self.fps_var = ctk.StringVar()
        ctk.CTkLabel(bar, textvariable=self.fps_var, font=ctk.CTkFont(size=11), text_color="gray").pack(side="right", padx=8)

    def _build_train_tab(self):
        tab = self.tab_train
        f = ctk.CTkFrame(tab); f.pack(fill="x", padx=10, pady=10)

        ctk.CTkLabel(f, text="数据集目录:").pack(anchor="w", padx=8, pady=(8, 0))
        r = ctk.CTkFrame(f, fg_color="transparent"); r.pack(fill="x", padx=8, pady=2)
        self.dataset_var = ctk.StringVar(value=str(PROJECT_DIR / "datasets" / "default"))
        ctk.CTkEntry(r, textvariable=self.dataset_var).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(r, text="浏览", width=60, command=lambda: self.dataset_var.set(
            filedialog.askdirectory(initialdir=str(PROJECT_DIR)) or self.dataset_var.get())).pack(side="left", padx=(4, 0))

        ctk.CTkLabel(f, text="模型大小:").pack(anchor="w", padx=8, pady=(8, 0))
        self.model_size_var = ctk.StringVar(value="n")
        ctk.CTkComboBox(f, values=["n", "s", "m", "l"], variable=self.model_size_var, width=100).pack(anchor="w", padx=8, pady=2)

        ctk.CTkLabel(f, text="训练轮数:").pack(anchor="w", padx=8, pady=(8, 0))
        self.epochs_var = ctk.StringVar(value="50")
        ctk.CTkEntry(f, textvariable=self.epochs_var, width=80).pack(anchor="w", padx=8, pady=2)

        ctk.CTkLabel(f, text="导出模型名:").pack(anchor="w", padx=8, pady=(8, 0))
        ctk.CTkLabel(f, text="训练完保存为这个名字（如 ore, creature）",
                     font=ctk.CTkFont(size=10), text_color="gray").pack(anchor="w", padx=8)
        self.model_name_var = ctk.StringVar(value="best")
        ctk.CTkEntry(f, textvariable=self.model_name_var, width=140).pack(anchor="w", padx=8, pady=2)

        ctk.CTkLabel(f, text="设备:").pack(anchor="w", padx=8, pady=(8, 0))
        devices = ["cuda", "cpu"] if HAS_CUDA else ["cpu"]
        self.device_var = ctk.StringVar(value=devices[0])
        ctk.CTkComboBox(f, values=devices, variable=self.device_var, width=120).pack(anchor="w", padx=8, pady=2)

        r = ctk.CTkFrame(f, fg_color="transparent"); r.pack(fill="x", padx=8, pady=(10, 2))
        ctk.CTkButton(r, text="创建数据集目录", command=self._create_dataset).pack(side="left", padx=(0, 4))
        ctk.CTkButton(r, text="启动标注工具", command=self._launch_label_tool).pack(side="left", padx=(0, 4))
        ctk.CTkButton(r, text="开始训练", command=self._start_training, fg_color="#1565C0").pack(side="left")

        self.train_status = ctk.CTkLabel(f, text="状态: 等待操作", font=ctk.CTkFont(size=11))
        self.train_status.pack(anchor="w", padx=8, pady=(4, 8))

    def _build_route_tab(self):
        tab = self.tab_route

        # 上栏：路线操作按钮
        bar = ctk.CTkFrame(tab)
        bar.pack(fill="x", padx=10, pady=(10, 4))
        ctk.CTkLabel(bar, text="路线规划", font=ctk.CTkFont(size=16, weight="bold")).pack(side="left", padx=8)
        ctk.CTkButton(bar, text="加载路线", command=self._load_route_file, width=80).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="保存路线", command=self._save_route_file, width=80).pack(side="left", padx=4)
        ctk.CTkButton(bar, text="清空路线", command=self._clear_route, width=80).pack(side="left", padx=4)

        # 操作栏：导航控制
        bar2 = ctk.CTkFrame(tab)
        bar2.pack(fill="x", padx=10, pady=2)
        ctk.CTkButton(bar2, text="开始导航", command=self._start_route_nav, fg_color="#1565C0", width=80).pack(side="right", padx=4)
        ctk.CTkButton(bar2, text="停止", command=self._stop_route_nav, fg_color="#C62828", width=60).pack(side="right", padx=4)

        # 状态栏
        self.route_status = ctk.CTkLabel(tab, text="左键标途经点 | 右键删点 | 滚轮缩放 | 拖拽移动",
                                          font=ctk.CTkFont(size=11), text_color="gray")
        self.route_status.pack(fill="x", padx=14, pady=2)

        # 地图画布
        self.route_canvas = ctk.CTkCanvas(tab, bg="#1a1a1a", highlightthickness=0)
        self.route_canvas.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # 启动后自动加载大地图并显示
        self.after(500, self._auto_load_and_show_map)

    def _auto_load_and_show_map(self):
        """自动加载大地图"""
        gmt_map = PROJECT_DIR / "maps" / "big_map.png"
        if not gmt_map.exists():
            self.route_status.configure(text="未找到 maps/big_map.png")
            return

        def _load():
            img = cv2.imread(str(gmt_map))
            if img is not None:
                self._big_map = img
                self._route_waypoints = []
                logger.info("大地图已加载: %sx%s", img.shape[1], img.shape[0])
                # 延迟 500ms 等画布渲染完再显示
                self.after(500, self._show_big_map_safe)

        threading.Thread(target=_load, daemon=True).start()

    def _show_big_map_safe(self):
        """安全显示大地图（在 GUI 线程调用）"""
        if not hasattr(self, '_big_map') or self._big_map is None:
            return
        try:
            self._show_big_map()
            self.route_status.configure(
                text=f"大地图已加载 ({self._big_map.shape[1]}x{self._big_map.shape[0]}) | 左键标点 | 右键删点")
        except Exception as e:
            logger.warning(f"显示大地图失败: {e}")

    # ========== 模型管理 ==========
    def _refresh_models(self):
        md = PROJECT_DIR / "models"
        if md.exists():
            files = sorted(md.glob("*.pt"), key=lambda p: p.stat().st_size, reverse=True)
            self._model_paths = {f.name: str(f) for f in files}
            self.model_combo.configure(values=list(self._model_paths.keys()))
            if self._model_paths:
                self.model_combo.set(list(self._model_paths.keys())[0])

    def _load_model(self):
        name = self.model_combo.get()
        if name not in getattr(self, '_model_paths', {}):
            messagebox.showerror("错误", "请先选择模型"); return
        ok = self.vision.load(self._model_paths[name])
        if ok:
            self.status_var.set(f"模型就绪: {name} — 类别: {list(self.vision.names.values())}")
        else:
            messagebox.showerror("错误", "模型加载失败")

    # ========== 预览 ==========
    def _start_preview(self):
        self.preview_active = True
        threading.Thread(target=self._capture_loop, daemon=True).start()
        self._update_preview()

    def _capture_loop(self):
        while self.preview_active:
            try:
                f = self.capture.grab()
                if f is not None: self._preview_frame = f
            except Exception:
                pass  # 截图失败不中断循环 (logging 会导致大量重复日志)
            time.sleep(0.05)

    def _update_preview(self):
        if not self.preview_active: return
        try:
            frame = self._preview_frame
            if frame is not None:
                cw, ch = max(self.canvas.winfo_width(), 100), max(self.canvas.winfo_height(), 100)
                cw, ch = min(cw, 1000), min(ch, 750)
                h, w = frame.shape[:2]
                s = min(cw / w, ch / h)
                small = cv2.resize(frame, (int(w * s), int(h * s)), interpolation=cv2.INTER_NEAREST)
                rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
                old = getattr(self, '_tk', None)
                self._tk = ImageTk.PhotoImage(Image.fromarray(rgb))
                if old: del old
                self.canvas.delete("all")
                self.canvas.create_image(cw // 2, ch // 2, image=self._tk)
                now = time.time()
                self._fps_times.append(now)
                self._fps_times = [t for t in self._fps_times if now - t < 2]
                if len(self._fps_times) > 1:
                    self.fps_var.set(f"{len(self._fps_times) / (now - self._fps_times[0]):.0f} FPS")
        except Exception:
            pass  # UI 更新失败不致命
        self.after(33, self._update_preview)

    # ========== 采矿 ==========
    def _start_mining(self):
        if not self.vision.loaded:
            messagebox.showwarning("提示", "请先加载模型")
            return
        self.automator.start()
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="normal", text="暂停")
        self.status_var.set("采矿中 (多模型联动)")
        def run():
            self.automator.walk_to_mine()
            self.after(0, self._mining_stopped)
        threading.Thread(target=run, daemon=True).start()
        self.after(500, self._update_stats_loop)

    def _pause_mining(self):
        if self.automator.paused:
            self.automator.resume(); self.pause_btn.configure(text="暂停")
        else:
            self.automator.pause(); self.pause_btn.configure(text="继续")

    def _stop_mining(self):
        self.automator.stop(); self._mining_stopped()

    def _mining_stopped(self):
        self.start_btn.configure(state="normal")
        self.pause_btn.configure(state="disabled", text="暂停")
        self.status_var.set("已停止")
        self._update_stats()

    def _update_stats_loop(self):
        if self.automator.running: self._update_stats(); self.after(1000, self._update_stats_loop)

    def _update_stats(self):
        s = self.automator.stats
        self.stats_label.configure(text=f"采集: {s['clicks']} | 检测: {s['detections']} | 循环: {s['loops']}")

    # ========== 训练 ==========
    def _create_dataset(self):
        from src.training.trainer import create_dataset_structure
        classes = ["ore", "creature", "obstacle", "character"]
        d = self.dataset_var.get()
        create_dataset_structure(d, classes)
        self.train_status.configure(text=f"数据集已创建: {d}")

    def _launch_label_tool(self):
        from src.training.label_tool import launch_label_tool
        img_dir = PROJECT_DIR / "datasets" / "default" / "images" / "train"
        # 自动创建目录
        img_dir.mkdir(parents=True, exist_ok=True)
        (PROJECT_DIR / "datasets" / "default" / "labels" / "train").mkdir(parents=True, exist_ok=True)

        if not any(img_dir.iterdir()):
            screenshots = PROJECT_DIR / "screenshots"
            screenshots.mkdir(exist_ok=True)
            if any(screenshots.iterdir()):
                img_dir = screenshots
            else:
                messagebox.showinfo("提示",
                    "数据集目录为空。\n\n"
                    "请先将游戏截图放入:\n"
                    f"{img_dir}\n\n"
                    "或点击「创建数据集目录」按钮自动生成目录结构")
                return
        classes = ["ore", "creature", "obstacle", "character"]
        launch_label_tool(str(img_dir), classes,
                          output_dir=str(PROJECT_DIR / "datasets" / "default" / "labels" / "train"),
                          parent=None)  # None=独立窗口, 避免 CTk 兼容问题

    def _start_training(self):
        from src.training.trainer import YOLOTrainer
        dataset = self.dataset_var.get()
        if not Path(dataset).exists():
            messagebox.showerror("错误", "数据集目录不存在"); return
        self.train_status.configure(text="训练中...")
        def _train():
            try:
                t = YOLOTrainer(dataset, model_size=self.model_size_var.get())
                epoch = int(self.epochs_var.get())
                t.train(epochs=epoch, device=self.device_var.get())
                out = t.export_best(str(PROJECT_DIR / "models"), search_dir=str(PROJECT_DIR),
                                    name=self.model_name_var.get().strip() or "best")
                self.after(0, lambda o=out: self.train_status.configure(text=f"完成! {o}"))
                self.after(0, self._refresh_models)
            except Exception as e:
                msg = str(e)
                self.after(0, lambda m=msg: self.train_status.configure(text=f"失败: {m}"))
        threading.Thread(target=_train, daemon=True).start()

    # ========== 路线规划 ==========
    def _load_big_map(self):
        path = filedialog.askopenfilename(filetypes=[("图片", "*.png *.jpg *.jpeg")])
        if not path: return
        img = cv2.imread(path)
        if img is None: return
        self._big_map = img
        self._route_waypoints = []
        self._show_big_map()
        self.route_status.configure(text="点击地图添加途经点, 右键删最后点")

    def _show_big_map(self):
        """显示大地图（视口模式：只渲染可见区域，不压缩像素，无缩放限制，居中）"""
        # 解除旧事件绑定
        for ev in ("<Button-1>", "<B1-Motion>", "<ButtonRelease-1>", "<Button-3>", "<MouseWheel>"):
            self.route_canvas.unbind(ev)

        h, w = self._big_map.shape[:2]

        # 画布尺寸（所有嵌套函数都能访问）
        self._cw = max(self.route_canvas.winfo_width(), 200)
        self._ch = max(self.route_canvas.winfo_height(), 200)

        # 相机状态：视口中心在大地图上的坐标 + 缩放倍数
        if not hasattr(self, '_map_cam_x'):
            self._map_cam_x = w / 2.0   # 初始：地图中心
            self._map_cam_y = h / 2.0
        if not hasattr(self, '_map_zoom'):
            self._map_zoom = 1.0  # 1.0 = 1个地图像素 = 1个屏幕像素

        self._map_dragging = False
        self._map_drag_start = None

        def redraw():
            """视口裁剪渲染：只处理可见区域"""
            zoom = self._map_zoom

            # 可见区域在大地图上的范围
            vp_w = self._cw / zoom  # 视口宽度（地图像素）
            vp_h = self._ch / zoom
            vp_x1 = self._map_cam_x - vp_w / 2
            vp_y1 = self._map_cam_y - vp_h / 2

            # 裁剪到大地图范围
            src_x1 = max(0, int(vp_x1))
            src_y1 = max(0, int(vp_y1))
            src_x2 = min(w, int(vp_x1 + vp_w) + 1)
            src_y2 = min(h, int(vp_y1 + vp_h) + 1)

            if src_x2 <= src_x1 or src_y2 <= src_y1:
                return

            # 裁剪可见区域（原始像素，不压缩）
            crop = self._big_map[src_y1:src_y2, src_x1:src_x2]

            # 缩放到画布尺寸
            crop_h, crop_w = crop.shape[:2]
            disp_w = int(crop_w * zoom)
            disp_h = int(crop_h * zoom)
            if disp_w < 1 or disp_h < 1:
                return
            displayed = cv2.resize(crop, (disp_w, disp_h), interpolation=cv2.INTER_NEAREST)

            rgb = cv2.cvtColor(displayed, cv2.COLOR_BGR2RGB)
            self._map_tk = ImageTk.PhotoImage(Image.fromarray(rgb))
            self.route_canvas.delete("all")

            # 居中放置
            ox = int((self._cw - disp_w) / 2)
            oy = int((self._ch - disp_h) / 2)
            # 修正：如果裁剪区域不从 (0,0) 开始，需要偏移
            ox -= int((vp_x1 - src_x1) * zoom)
            oy -= int((vp_y1 - src_y1) * zoom)

            self.route_canvas.create_image(ox, oy, anchor="nw", image=self._map_tk)

            # 存储变换参数（用于坐标转换）
            self._map_scale = zoom
            self._map_ox = ox - int(src_x1 * zoom)
            self._map_oy = oy - int(src_y1 * zoom)

            self._draw_waypoints()

        def on_down(e):
            self._map_dragging = True
            self._map_drag_start = (e.x, e.y)
            self._map_drag_origin = (e.x, e.y)

        def on_move(e):
            if self._map_dragging and self._map_drag_start:
                dx = e.x - self._map_drag_start[0]
                dy = e.y - self._map_drag_start[1]
                # 移动相机（反方向）
                self._map_cam_x -= dx / self._map_zoom
                self._map_cam_y -= dy / self._map_zoom
                self._map_drag_start = (e.x, e.y)
                redraw()

        def on_up(e):
            if self._map_dragging:
                self._map_dragging = False
                ox, oy = self._map_drag_origin
                moved = math.hypot(e.x - ox, e.y - oy)
                if moved < 5:
                    # 点击：添加途经点
                    mx = self._map_cam_x + (e.x - self._cw / 2) / self._map_zoom
                    my = self._map_cam_y + (e.y - self._ch / 2) / self._map_zoom
                    mx = max(0, min(w, mx))
                    my = max(0, min(h, my))
                    self._route_waypoints.append((int(mx), int(my), f"点{len(self._route_waypoints)+1}"))
                    self._draw_waypoints()
                    self.route_status.configure(text=f"途经点: {len(self._route_waypoints)}")
                self._map_drag_start = None

        def on_right(e):
            if self._route_waypoints:
                self._route_waypoints.pop()
                self._draw_waypoints()
                self.route_status.configure(text=f"途经点: {len(self._route_waypoints)}")

        def on_zoom(e):
            # 缩放（无限制）
            factor = 1.3 if e.delta > 0 else 1 / 1.3
            self._map_zoom *= factor

            # 缩放后，保持鼠标指向的地图点不变
            mx_before = self._map_cam_x + (e.x - self._cw / 2) / (self._map_zoom / factor)
            my_before = self._map_cam_y + (e.y - self._ch / 2) / (self._map_zoom / factor)
            self._map_cam_x = mx_before - (e.x - self._cw / 2) / self._map_zoom
            self._map_cam_y = my_before - (e.y - self._ch / 2) / self._map_zoom

            redraw()

        def on_resize(e):
            self._cw = max(self.route_canvas.winfo_width(), 100)
            self._ch = max(self.route_canvas.winfo_height(), 100)
            redraw()

        self.route_canvas.bind("<Button-1>", on_down)
        self.route_canvas.bind("<B1-Motion>", on_move)
        self.route_canvas.bind("<ButtonRelease-1>", on_up)
        self.route_canvas.bind("<Button-3>", on_right)
        self.route_canvas.bind("<MouseWheel>", on_zoom)
        self.route_canvas.bind("<Configure>", on_resize)
        redraw()

    def _draw_waypoints(self):
        """在画布上绘制途经点和连线"""
        if not hasattr(self, '_route_waypoints') or not self._route_waypoints:
            return
        if not hasattr(self, '_map_cam_x'):
            return

        self.route_canvas.delete("wp")
        zoom = self._map_zoom
        self._cw = max(self.route_canvas.winfo_width(), 100)
        self._ch = max(self.route_canvas.winfo_height(), 100)
        colors = ["#00FF00", "#FFD700", "#FF4444", "#4488FF"] * 10

        def map_to_canvas(mx, my):
            """大地图坐标 → 画布坐标"""
            cx = int((mx - self._map_cam_x) * zoom + self._cw / 2)
            cy = int((my - self._map_cam_y) * zoom + self._ch / 2)
            return cx, cy

        for i, (mx, my, name) in enumerate(self._route_waypoints):
            cx, cy = map_to_canvas(mx, my)
            c = colors[i % len(colors)]
            self.route_canvas.create_oval(cx-5, cy-5, cx+5, cy+5, fill=c, outline="white", width=1, tags="wp")
            self.route_canvas.create_text(cx, cy-12, text=name, fill=c, font=("", 9), tags="wp")
            if i > 0:
                px, py = map_to_canvas(self._route_waypoints[i-1][0], self._route_waypoints[i-1][1])
                self.route_canvas.create_line(px, py, cx, cy, fill=c, width=2, dash=(4, 2), tags="wp")

    def _clear_route(self):
        self._route_waypoints = []
        self._show_big_map() if hasattr(self, '_big_map') else None
        self.route_status.configure(text="路线已清空")

    def _save_route_file(self):
        if not hasattr(self, '_route_waypoints') or not self._route_waypoints:
            messagebox.showwarning("提示", "没有途经点, 请先在大地图上点击标记")
            return
        import json
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = PROJECT_DIR / "routes" / f"route_{ts}.json"
        path.parent.mkdir(exist_ok=True)
        data = {"waypoints": self._route_waypoints}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.route_status.configure(text=f"路线已保存: {path.name}")
        logger.info(f"路线已保存到: {path.name}")

    def _load_route_file(self):
        path = filedialog.askopenfilename(filetypes=[("路线", "*.json")],
                                           initialdir=str(PROJECT_DIR / "routes"))
        if not path: return
        import json
        with open(path, encoding="utf-8") as f: data = json.load(f)
        # 兼容两种格式: waypoints (标准) 和 points (GMT)
        if "waypoints" in data:
            self._route_waypoints = data["waypoints"]
        elif "points" in data:
            self._route_waypoints = [
                [p["x"], p["y"], p.get("label", f"点{i}")]
                for i, p in enumerate(data["points"], 1)
            ]
            logger.info("从 GMT 格式转换: %d 个点", len(self._route_waypoints))
        else:
            messagebox.showwarning("格式错误", "路线文件格式无法识别")
            return
        if hasattr(self, '_big_map'): self._draw_waypoints()
        self.route_status.configure(text=f"路线已加载: {len(self._route_waypoints)} 个点")

    def _auto_detect_mm(self):
        """自动检测小地图位置"""
        frame = self._preview_frame if self._preview_frame is not None else self.capture.grab()
        if frame is None:
            self.route_status.configure(text="无法获取截图")
            return
        from src.engine.minimap_detector import MinimapDetector
        detector = MinimapDetector()
        region = detector.detect(frame)
        if region:
            self._mm_region = region
            x, y, w, h = region
            self.route_status.configure(text=f"自动检测到小地图: ({x},{y}) {w}x{h}")
            logger.info(f"自动检测小地图: {region}")
            self._save_mm_region(region)
        else:
            self.route_status.configure(text="自动检测失败，请手动框选小地图")
            logger.warning("自动检测小地图失败")

    def _freeze_for_mm(self):
        """冻结画面让用户框选小地图区域"""
        self._mm_frame = self._preview_frame if self._preview_frame is not None else self.capture.grab()
        self._mm_drawing = False
        self._mm_start = None

        # 在预览画布上显示提示
        self.route_canvas.delete("all")
        cw, ch = self.route_canvas.winfo_width(), self.route_canvas.winfo_height()
        h, w = self._mm_frame.shape[:2]
        s = min(cw / w, ch / h)
        small = cv2.resize(self._mm_frame, (int(w * s), int(h * s)))
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        self._mm_tk = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.route_canvas.create_image(cw // 2, ch // 2, image=self._mm_tk)
        self.route_canvas.create_text(cw // 2, 20, text="鼠标拖拽框选小地图区域, 松开即确认",
                                       fill="yellow", font=("", 12))

        def on_down(e): self._mm_drawing = True; self._mm_start = (e.x, e.y)
        def on_drag(e):
            if self._mm_drawing and self._mm_start:
                self.route_canvas.delete("mm_rect")
                x1, y1 = self._mm_start
                self.route_canvas.create_rectangle(x1, y1, e.x, e.y, outline="#00FF00",
                                                    width=2, tags="mm_rect")
        def on_up(e):
            self._mm_drawing = False
            if self._mm_start:
                x1, y1 = self._mm_start
                x2, y2 = e.x, e.y
                # 转回原始坐标
                ox1 = int((min(x1, x2) - (cw - int(w * s)) // 2) / s)
                oy1 = int((min(y1, y2) - (ch - int(h * s)) // 2) / s)
                ox2 = int((max(x1, x2) - (cw - int(w * s)) // 2) / s)
                oy2 = int((max(y1, y2) - (ch - int(h * s)) // 2) / s)
                ox1, oy1 = max(0, ox1), max(0, oy1)
                ox2, oy2 = min(w, ox2), min(h, oy2)
                self._mm_region = (ox1, oy1, ox2 - ox1, oy2 - oy1)
                self.route_status.configure(text=f"小地图区域: {self._mm_region}")

        self.route_canvas.bind("<Button-1>", on_down)
        self.route_canvas.bind("<B1-Motion>", on_drag)
        self.route_canvas.bind("<ButtonRelease-1>", on_up)
        self.route_status.configure(text="请在下方画布上拖拽框选小地图")

    def _start_route_nav(self):
        """开始导航"""
        # 1. 加载大地图
        if not hasattr(self, '_big_map') or self._big_map is None:
            gmt_map = PROJECT_DIR / "maps" / "big_map.png"
            if gmt_map.exists():
                self._big_map = cv2.imread(str(gmt_map))
                logger.info("大地图已加载: %sx%s", self._big_map.shape[1], self._big_map.shape[0])
            else:
                messagebox.showwarning("提示", "请先导入大地图"); return

        # 2. 小地图区域
        if not hasattr(self, '_mm_region') or not self._mm_region:
            if not self._load_mm_region():
                self._mm_region = None

        # 3. 加载路线
        if not hasattr(self, '_route_waypoints') or len(self._route_waypoints) < 2:
            route_files = sorted((PROJECT_DIR / "routes").glob("**/*.json"),
                                 key=lambda p: p.stat().st_mtime, reverse=True)
            if route_files:
                import json
                with open(route_files[0], encoding="utf-8") as f:
                    data = json.load(f)
                # 兼容两种格式
                if "waypoints" in data:
                    self._route_waypoints = data["waypoints"]
                elif "points" in data:
                    self._route_waypoints = [
                        [p["x"], p["y"], p.get("label", f"点{i}")]
                        for i, p in enumerate(data["points"], 1)
                    ]
            if not hasattr(self, '_route_waypoints') or len(self._route_waypoints) < 2:
                messagebox.showwarning("提示", "需要至少2个途经点"); return

        from src.automation.route_planner import RoutePlanner
        self._route_planner = RoutePlanner(self.controller, self.capture)
        self._route_planner.set_logic_map(self._big_map)
        if self._mm_region:
            self._route_planner.set_minimap_region(*self._mm_region)
        # 否则 route_planner 会自动用霍夫圆检测小地图
        self._route_planner.waypoints = list(self._route_waypoints)

        logger.info("%d 个途经点, 开始导航", len(self._route_waypoints))
        self.route_status.configure(text="路线导航运行中...")

        def nav():
            try:
                self._route_planner.run_route(self.automator)
                self.after(0, lambda: self.route_status.configure(text="导航完成"))
            except Exception as e:
                import traceback
                traceback.print_exc()
                msg = str(e)
                self.after(0, lambda m=msg: self.route_status.configure(text=f"导航错误: {m}"))
        threading.Thread(target=nav, daemon=True).start()

    def _stop_route_nav(self):
        if hasattr(self, '_route_planner') and self._route_planner is not None:
            self._route_planner.stop()
        self.route_status.configure(text="导航已停止")

    # ========== 热键 ==========
    def _setup_hotkeys(self):
        auto_ss_active = [False]   # 用列表让闭包可修改

        def ss():
            f = self._preview_frame if self._preview_frame is not None else self.capture.grab()
            p = PROJECT_DIR / "screenshots" / f"auto_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            p.parent.mkdir(exist_ok=True)
            cv2.imwrite(str(p), f)

        def toggle_auto_ss():
            auto_ss_active[0] = not auto_ss_active[0]
            if auto_ss_active[0]:
                try:
                    interval = float(self.auto_ss_interval_var.get())
                except ValueError:
                    interval = 2.0
                self._auto_ss_interval = max(0.1, interval)  # 最小 0.1 秒
            state = "ON" if auto_ss_active[0] else "OFF"
            iv = getattr(self, '_auto_ss_interval', 2.0)
            self.after(0, lambda: self.status_var.set(f"计时截图: {state} (间隔{iv}s)"))
            logger.info("计时截图: %s (间隔%ss)", state, iv)
            if auto_ss_active[0]:
                self._auto_ss_loop(ss, auto_ss_active, iv)

        stop_cb = lambda: (self.automator.stop(), self._stop_route_nav(),
                            self._mining_stopped(), logger.info("紧急停止"))
        self._hotkeys = create_hotkey(self, {
            "L": (ss, ["ctrl"]),
            "T": (toggle_auto_ss, ["ctrl"]),
            "Q": (stop_cb, ["ctrl", "shift"]),
        })

    def _auto_ss_loop(self, ss_fn, active, interval):
        if not active[0]:
            return
        ss_fn()
        count = len(list((PROJECT_DIR / "screenshots").glob("auto_*.png")))
        self.status_var.set(f"计时截图 ON | 已截{count}张 | 间隔{interval}s")
        self.after(int(interval * 1000), lambda: self._auto_ss_loop(ss_fn, active, interval))

    def _save_mm_region(self, region):
        """保存小地图区域到文件"""
        import json
        path = PROJECT_DIR / "minimap_region.json"
        with open(path, "w") as f:
            json.dump({"region": list(region)}, f)
        logger.info(f"小地图区域已保存: {region}")

    def _load_mm_region(self):
        """从文件加载小地图区域"""
        import json
        path = PROJECT_DIR / "minimap_region.json"
        if path.exists():
            with open(path) as f:
                data = json.load(f)
            region = data.get("region")
            if region and len(region) == 4:
                self._mm_region = tuple(region)
                logger.info(f"加载已保存的小地图区域: {self._mm_region}")
                return True
        return False

    def _on_close(self):
        self.preview_active = False
        self.automator.stop()
        if hasattr(self, '_route_planner') and self._route_planner is not None:
            self._route_planner.stop()
        if hasattr(self, '_hotkeys'): self._hotkeys.cleanup()
        # 释放所有可能被按住的键
        for key in ['w', 'a', 's', 'd']:
            try:
                self.controller.key_up(key)
            except Exception:
                pass
        if hasattr(self, '_tk'): del self._tk
        self.capture.sct.close()
        self.destroy()
        os._exit(0)  # 强制退出，杀死所有 daemon 线程


if __name__ == "__main__":
    GameAuto().mainloop()
