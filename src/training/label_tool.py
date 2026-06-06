"""
数据标注工具 - 在截图上框选目标，生成 YOLO 格式标注文件
"""
import os
import tkinter as tk
import logging
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

logger = logging.getLogger("gameauto.label_tool")

import cv2
import numpy as np
from PIL import Image, ImageTk


class LabelTool:
    """简易 YOLO 标注工具"""

    def __init__(self, image_dir: str, classes: list, output_dir: str = None, parent=None):
        self.image_dir = Path(image_dir)
        self.classes = classes
        self.output_dir = Path(output_dir) if output_dir else self.image_dir.parent / "labels"
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.images = sorted([
            f for f in os.listdir(image_dir)
            if f.lower().endswith(('.png', '.jpg', '.jpeg', '.bmp'))
        ])
        if not self.images:
            raise ValueError(f"目录 {image_dir} 中没有图片文件")

        self.current_idx = 0
        self.current_class = 0
        self.bboxes = []
        self._dirty = False          # 有未保存的修改才写盘
        self.drawing = False
        self.start_x = self.start_y = 0
        self.img_w = self.img_h = 1
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0

        self._cache = {}          # idx -> PhotoImage
        self._cache_scale = None  # 缓存时的 (cw, ch)
        self._preload_id = None   # 预加载 after ID

        self.parent = parent
        self.root = tk.Toplevel(parent)  # 不创建新的 Tk 根
        self.root.title("AI 数据标注工具 — YOLO 格式")
        self.root.geometry("1100x750")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build_ui()
        self.root.update()
        self._load_image()

    def _on_close(self):
        """关闭窗口时清理资源"""
        if self._preload_id is not None:
            self.root.after_cancel(self._preload_id)
        self._cache.clear()
        self.root.destroy()

    def _build_ui(self):
        # 顶部工具栏
        toolbar = ttk.Frame(self.root)
        toolbar.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        ttk.Button(toolbar, text="打开图片目录", command=self._open_dir).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="上一张 (A)", command=self._prev_image).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="下一张 (D)", command=self._next_image).pack(side=tk.LEFT, padx=3)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        ttk.Label(toolbar, text="类别:").pack(side=tk.LEFT)
        self.class_var = tk.StringVar(value=self.classes[0] if self.classes else "")
        self.class_combo = ttk.Combobox(toolbar, textvariable=self.class_var,
                                        values=self.classes, width=12, state="readonly")
        self.class_combo.pack(side=tk.LEFT, padx=3)
        self.class_combo.bind("<<ComboboxSelected>>", self._on_class_change)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=2)

        ttk.Button(toolbar, text="删除最后框 (Z)", command=self._undo_box).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="清空所有框", command=self._clear_boxes).pack(side=tk.LEFT, padx=3)
        ttk.Button(toolbar, text="保存标注 (S)", command=self._save_labels).pack(side=tk.LEFT, padx=3)

        # 状态栏
        self.status_var = tk.StringVar()
        status = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status.pack(side=tk.BOTTOM, fill=tk.X)

        # 画布
        self.canvas = tk.Canvas(self.root, bg="gray20", cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 事件绑定
        self.canvas.bind("<ButtonPress-1>", self._on_mouse_down)
        self.canvas.bind("<B1-Motion>", self._on_mouse_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_mouse_up)
        self.canvas.bind("<MouseWheel>", self._on_mouse_wheel)
        self.canvas.bind("<Configure>", self._on_resize)

        # 键盘快捷键 — 用单个 handler 处理所有键，大小写不敏感
        self.root.bind("<Key>", self._on_key)
        # 确保画布不会拦截键盘事件
        self.canvas.bind("<Key>", self._on_key)
        self.class_combo.bind("<Key>", self._on_key)

    def _resize_image(self, img_rgb):
        """将图片缩放到适合画布显示的大小"""
        cw = min(self.canvas.winfo_width(), 1200)   # 限制最大尺寸，避免 4K 显示器占用过多内存
        ch = min(self.canvas.winfo_height(), 900)
        cw = max(cw, 10)
        ch = max(ch, 10)
        h, w = img_rgb.shape[:2]
        scale = min(cw / w, ch / h)
        new_w = int(w * scale)
        new_h = int(h * scale)
        self.scale = scale
        self.offset_x = (cw - new_w) // 2
        self.offset_y = (ch - new_h) // 2
        return cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_NEAREST)

    def _load_image(self):
        if not self.images:
            self.canvas.delete("all")
            self.canvas.create_text(400, 300, text="没有图片\n请点击「打开图片目录」选择包含 .png/.jpg 图片的文件夹",
                                     fill="gray", font=("", 14), tags="placeholder")
            return
        self.canvas.delete("all")
        self.bboxes = []
        self._dirty = False

        path = str(self.image_dir / self.images[self.current_idx])
        img = cv2.imread(path)
        if img is None:
            return
        self.img_h, self.img_w = img.shape[:2]
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        cache_key = self.current_idx
        cw = max(self.canvas.winfo_width(), 10)
        ch = max(self.canvas.winfo_height(), 10)
        if cache_key in self._cache and self._cache_scale == (cw, ch):
            self.tk_image = self._cache[cache_key]
        else:
            resized = self._resize_image(img_rgb)
            self.tk_image = ImageTk.PhotoImage(Image.fromarray(resized))
            self._cache[cache_key] = self.tk_image
            self._cache_scale = (cw, ch)
            # 保留前后各 3 张缓存，平衡性能和内存
            stale = [k for k in self._cache if abs(k - self.current_idx) > 3]
            for k in stale:
                del self._cache[k]

        self.canvas.create_image(self.offset_x, self.offset_y, anchor=tk.NW, image=self.tk_image)
        self._load_existing_labels()
        self._update_status()
        # 只预加载下一张，减少 CPU 占用
        if self._preload_id is not None:
            self.root.after_cancel(self._preload_id)
        self._preload_id = self.root.after(300, self._preload_next)

    def _load_existing_labels(self):
        name = Path(self.images[self.current_idx]).stem
        label_path = self.output_dir / f"{name}.txt"
        if label_path.exists():
            with open(label_path) as f:
                for line in f:
                    parts = line.strip().split()
                    if len(parts) == 5:
                        cls_id = int(parts[0])
                        cx, cy, w, h = map(float, parts[1:])
                        self.bboxes.append((cls_id, cx, cy, w, h))
            self._redraw_boxes()

    def _to_yolo(self, x1, y1, x2, y2):
        """画布坐标 → YOLO 归一化坐标"""
        # 转回原始图像坐标
        ox1 = (x1 - self.offset_x) / self.scale
        oy1 = (y1 - self.offset_y) / self.scale
        ox2 = (x2 - self.offset_x) / self.scale
        oy2 = (y2 - self.offset_y) / self.scale
        # 计算中心点和宽高，归一化
        cx = ((ox1 + ox2) / 2) / self.img_w
        cy = ((oy1 + oy2) / 2) / self.img_h
        w = abs(ox2 - ox1) / self.img_w
        h = abs(oy2 - oy1) / self.img_h
        return (cx, cy, w, h)

    def _from_yolo(self, cls_id, cx, cy, w, h):
        """YOLO 归一化坐标 → 画布坐标"""
        ox = (cx - w / 2) * self.img_w
        oy = (cy - h / 2) * self.img_h
        ow = w * self.img_w
        oh = h * self.img_h
        x1 = ox * self.scale + self.offset_x
        y1 = oy * self.scale + self.offset_y
        x2 = (ox + ow) * self.scale + self.offset_x
        y2 = (oy + oh) * self.scale + self.offset_y
        return (x1, y1, x2, y2)

    def _redraw_boxes(self):
        """重绘所有标注框"""
        colors = ["#00FF00", "#FF0000", "#0000FF", "#FFFF00", "#FF00FF", "#00FFFF"]
        for cls_id, cx, cy, w, h in self.bboxes:
            x1, y1, x2, y2 = self._from_yolo(cls_id, cx, cy, w, h)
            color = colors[cls_id % len(colors)]
            self.canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2, tags="box")
            label = self.classes[cls_id] if cls_id < len(self.classes) else f"cls_{cls_id}"
            self.canvas.create_text(x1 + 2, y1 - 10, text=label, fill=color, anchor=tk.W, tags="box")

    def _on_mouse_down(self, event):
        self.drawing = True
        self.start_x = event.x
        self.start_y = event.y

    def _on_mouse_drag(self, event):
        if self.drawing:
            self.canvas.delete("preview")
            self.canvas.create_rectangle(
                self.start_x, self.start_y, event.x, event.y,
                outline="#00FF00", width=2, dash=(4, 2), tags="preview"
            )

    def _on_mouse_up(self, event):
        self.drawing = False
        self.canvas.delete("preview")
        x1, y1 = min(self.start_x, event.x), min(self.start_y, event.y)
        x2, y2 = max(self.start_x, event.x), max(self.start_y, event.y)
        if x2 - x1 > 5 and y2 - y1 > 5:
            cx, cy, w, h = self._to_yolo(x1, y1, x2, y2)
            self.bboxes.append((self.current_class, cx, cy, w, h))
            self._dirty = True
            self._redraw_boxes()
        self._update_status()

    def _on_key(self, event):
        """统一键盘处理，大小写不敏感"""
        k = event.keysym.lower()
        if k == 'a':
            self._prev_image()
        elif k == 'd':
            self._next_image()
        elif k == 's':
            self._save_labels()
        elif k == 'z':
            self._undo_box()
        elif k == 'q':
            self._switch_class(-1)
        elif k == 'e':
            self._switch_class(1)
        elif k == 'left':
            self._prev_image()
        elif k == 'right':
            self._next_image()

    def _on_mouse_wheel(self, event):
        delta = -1 if event.delta < 0 else 1
        self._switch_image(delta)

    def _preload_next(self):
        """只预加载下一张图片，延迟执行不阻塞当前操作"""
        idx = (self.current_idx + 1) % len(self.images)
        if idx in self._cache:
            return
        try:
            path = str(self.image_dir / self.images[idx])
            img = cv2.imread(path)
            if img is not None:
                img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                resized = self._resize_image(img_rgb)
                self._cache[idx] = ImageTk.PhotoImage(Image.fromarray(resized))
        except Exception:
            pass

    def _on_resize(self, event):
        self._cache.clear()
        self._cache_scale = None
        if hasattr(self, 'tk_image'):
            self._load_image()

    def _switch_class(self, delta):
        self.current_class = (self.current_class + delta) % len(self.classes)
        self.class_var.set(self.classes[self.current_class])

    def _on_class_change(self, event=None):
        name = self.class_var.get()
        if name in self.classes:
            self.current_class = self.classes.index(name)

    def _prev_image(self):
        self._switch_image(-1)

    def _next_image(self):
        self._switch_image(1)

    def _switch_image(self, delta):
        if not self.images:
            return
        if self._dirty:
            self._save_labels()
        self.current_idx = (self.current_idx + delta) % len(self.images)
        self._load_image()

    def _undo_box(self):
        if self.bboxes:
            self.bboxes.pop()
            self._dirty = True
            self.canvas.delete("box")
            self._redraw_boxes()
            self._update_status()

    def _clear_boxes(self):
        if self.bboxes:
            self.bboxes.clear()
            self._dirty = True
            self.canvas.delete("box")
            self._update_status()

    def _save_labels(self):
        """保存当前图片的标注（只在有修改时调用）"""
        if not self.images:
            return
        name = Path(self.images[self.current_idx]).stem
        label_path = self.output_dir / f"{name}.txt"
        if self.bboxes:
            with open(label_path, "w") as f:
                for cls_id, cx, cy, w, h in self.bboxes:
                    f.write(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
        elif label_path.exists():
            label_path.unlink()  # 框全删了就删文件
        self._dirty = False
        self.status_var.set(f"已保存: {label_path}")
        logger.info("已保存: %s", label_path)

    def _open_dir(self):
        project = Path(__file__).parent.parent.parent.resolve()
        candidates = [
            project / "datasets" / "default" / "images" / "train",
            project / "datasets" / "default" / "images",
            project / "screenshots",
            project,
            Path.home(),
        ]
        initial = str(project)
        for d in candidates:
            if d.exists():
                initial = str(d)
                break

        new_dir = filedialog.askdirectory(
            title="选择图片目录", parent=self.root, initialdir=initial,
        )
        if not new_dir:
            return

        self.image_dir = Path(new_dir)
        self.images = sorted([
            f for f in self.image_dir.iterdir()
            if f.suffix.lower() in ('.png', '.jpg', '.jpeg', '.bmp')
        ])
        if not self.images:
            messagebox.showwarning("无图片", f"该目录中没有支持的图片文件", parent=self.root)
            return

        # 自动匹配标注目录：images/train → labels/train，images/val → labels/val
        datasets_dir = project / "datasets" / "default"
        img_rel = None
        try:
            img_rel = self.image_dir.resolve().relative_to(datasets_dir / "images")
        except ValueError:
            pass
        if img_rel is not None:
            new_output = (datasets_dir / "labels" / img_rel).resolve()
            new_output.mkdir(parents=True, exist_ok=True)
            self.output_dir = new_output
            logger.info("标注输出目录更新: %s", new_output)

        self._cache.clear()
        self._cache_scale = None
        self.current_idx = 0
        self._load_image()

    def _update_status(self):
        if self.images:
            pct = (self.current_idx + 1) / len(self.images) * 100
            self.status_var.set(
                f"第 {self.current_idx + 1}/{len(self.images)} 张 ({pct:.0f}%) | "
                f"当前类别: {self.classes[self.current_class]} | "
                f"标注框: {len(self.bboxes)} 个 | "
                f"A/D=切换图片 S=保存 Z=撤销 Q/E=切换类别"
            )

    def run(self):
        self.root.mainloop()

    def cleanup(self):
        """释放所有缓存资源"""
        if self._preload_id is not None:
            self.root.after_cancel(self._preload_id)
        for k in list(self._cache.keys()):
            del self._cache[k]
        self._cache.clear()


def launch_label_tool(image_dir: str, classes: list, output_dir: str = None, parent=None):
    """启动标注工具"""
    tool = LabelTool(image_dir, classes, output_dir=output_dir, parent=parent)
    tool.run()
