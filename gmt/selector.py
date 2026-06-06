import tkinter as tk
import json
import os
import mss
from PIL import Image, ImageTk

CONFIG_FILE = "config.json"


class MinimapSelector:
    def __init__(self, root):
        self.root = root
        self.root.title("小地图校准器")

        # --- 窗口样式设置 ---
        self.root.overrideredirect(True)  # 去除系统窗口边框
        self.root.attributes("-topmost", True)  # 永远置顶
        self.root.attributes("-alpha", 0.5)  # 设置整体半透明(50%)，方便看透下方的游戏
        self.root.configure(bg='black')  # 背景纯黑

        # --- 初始化状态 ---
        self.size = 150
        self.x = 100
        self.y = 100

        # 从现有配置文件中读取上一次的位置
        self.load_initial_pos()

        # 设置初始位置和大小
        self.root.geometry(f"{self.size}x{self.size}+{self.x}+{self.y}")

        # --- 创建画布 ---
        self.canvas = tk.Canvas(root, bg='black', highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.draw_ui()

        # --- 绑定鼠标与键盘事件 ---
        self.canvas.bind("<ButtonPress-1>", self.on_press)  # 鼠标左键按下
        self.canvas.bind("<B1-Motion>", self.on_drag)  # 鼠标左键按住拖动

        # 绑定鼠标滚轮 (Windows)
        self.root.bind("<MouseWheel>", self.on_scroll)
        # 绑定鼠标滚轮 (Linux/Mac 兼容)
        self.root.bind("<Button-4>", lambda e: self.resize(10))
        self.root.bind("<Button-5>", lambda e: self.resize(-10))

        # 绑定回车键和双击触发预览
        self.root.bind("<Return>", self.prepare_preview)
        self.root.bind("<Double-Button-1>", self.prepare_preview)

        # 按 ESC 退出不保存
        self.root.bind("<Escape>", lambda e: self.root.destroy())

    def load_initial_pos(self):
        """尝试从 config.json 读取上次保存的坐标"""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    minimap = config.get("MINIMAP", {})
                    if minimap:
                        self.x = minimap.get("left", 100)
                        self.y = minimap.get("top", 100)
                        self.size = minimap.get("width", 150)
            except Exception:
                pass

    def draw_ui(self):
        """绘制界面元素 (圆形准星和提示文字)"""
        self.canvas.delete("all")
        w = 3  # 边框厚度

        # 1. 绘制表示小地图边界的绿色圆圈
        self.canvas.create_oval(w, w, self.size - w, self.size - w, outline="#00FF00", width=w)

        # 2. 绘制十字准星中心辅助线
        self.canvas.create_line(0, self.size // 2, self.size, self.size // 2, fill="#00FF00", dash=(4, 4))
        self.canvas.create_line(self.size // 2, 0, self.size // 2, self.size, fill="#00FF00", dash=(4, 4))

        # 3. 绘制操作提示文字
        self.canvas.create_text(self.size // 2, 15, text="左键拖动 | 滚轮缩放", fill="white",
                                font=("Microsoft YaHei", 9, "bold"))
        self.canvas.create_text(self.size // 2, self.size - 15, text="按 回车/双击 确认截取", fill="yellow",
                                font=("Microsoft YaHei", 9, "bold"))

    def on_press(self, event):
        """记录鼠标按下的起始位置"""
        self.start_x = event.x
        self.start_y = event.y

    def on_drag(self, event):
        """计算鼠标拖动的偏移量并移动窗口"""
        dx = event.x - self.start_x
        dy = event.y - self.start_y
        self.x += dx
        self.y += dy
        self.root.geometry(f"{self.size}x{self.size}+{self.x}+{self.y}")

    def on_scroll(self, event):
        """处理鼠标滚轮放大缩小"""
        if event.delta > 0:
            self.resize(10)  # 向上滚放大
        else:
            self.resize(-10)  # 向下滚缩小

    def resize(self, delta):
        """改变窗口尺寸"""
        self.size += delta
        if self.size < 80:
            self.size = 80  # 限制最小不能低于 80 像素

        self.root.geometry(f"{self.size}x{self.size}+{self.x}+{self.y}")
        self.draw_ui()

    def prepare_preview(self, event=None):
        """准备预览：先隐藏透明绿框，延迟一小会再截图，防止绿框被截进去"""
        self.root.withdraw()  # 隐藏主窗口
        self.root.update()  # 刷新UI状态
        # 延迟 100 毫秒等待系统将窗口从屏幕清除，然后执行截图
        self.root.after(100, self.show_preview_window)

    def show_preview_window(self):
        """执行截图并弹出预览窗口"""
        # --- 1. 使用 mss 截取真实画面 ---
        with mss.mss() as sct:
            monitor = {"top": self.y, "left": self.x, "width": self.size, "height": self.size}
            sct_img = sct.grab(monitor)
            # 转换为 PIL Image 以便在 Tkinter 中显示
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

        # --- 2. 创建预览窗口 ---
        self.preview_win = tk.Toplevel(self.root)
        self.preview_win.title("确认小地图截取区域")
        self.preview_win.attributes("-topmost", True)

        # 将预览窗口居中显示在屏幕上
        win_width, win_height = max(300, self.size + 100), self.size + 150
        screen_w = self.preview_win.winfo_screenwidth()
        screen_h = self.preview_win.winfo_screenheight()
        pos_x = (screen_w - win_width) // 2
        pos_y = (screen_h - win_height) // 2
        self.preview_win.geometry(f"{win_width}x{win_height}+{pos_x}+{pos_y}")
        self.preview_win.configure(bg="#2b2b2b")

        # --- 3. 显示截图 ---
        self.tk_img = ImageTk.PhotoImage(img)  # 必须保持引用
        img_label = tk.Label(self.preview_win, image=self.tk_img, bg="black")
        img_label.pack(pady=15)

        # --- 4. 显示坐标和尺寸信息 ---
        info_text = f"X: {self.x}  |  Y: {self.y}  |  尺寸: {self.size} x {self.size}"
        tk.Label(self.preview_win, text=info_text, fg="white", bg="#2b2b2b",
                 font=("Microsoft YaHei", 10, "bold")).pack(pady=5)

        # --- 5. 底部按钮区域 ---
        btn_frame = tk.Frame(self.preview_win, bg="#2b2b2b")
        btn_frame.pack(pady=10)

        # 重新截取按钮：销毁预览窗，恢复绿框窗
        def retake():
            self.preview_win.destroy()
            self.root.deiconify()  # 恢复显示主窗口

        # 确定按钮：保存配置并彻底退出
        def confirm():
            self.save_config()
            self.root.destroy()

        btn_retake = tk.Button(btn_frame, text="重新截取", command=retake, width=12,
                               font=("Microsoft YaHei", 9), bg="#555555", fg="white", relief=tk.FLAT)
        btn_retake.pack(side=tk.LEFT, padx=15)

        btn_confirm = tk.Button(btn_frame, text="确 定", command=confirm, width=12,
                                font=("Microsoft YaHei", 9, "bold"), bg="#4CAF50", fg="white", relief=tk.FLAT)
        btn_confirm.pack(side=tk.RIGHT, padx=15)

        # 在预览窗口按回车也可以直接确定，按 ESC 重新截取
        self.preview_win.bind("<Return>", lambda e: confirm())
        self.preview_win.bind("<Escape>", lambda e: retake())

    def save_config(self):
        """将当前坐标写入 config.json"""
        config_data = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
            except Exception:
                pass

        # 更新 JSON 字典中的 MINIMAP 节点
        config_data["MINIMAP"] = {
            "top": self.y,
            "left": self.x,
            "width": self.size,
            "height": self.size
        }

        # 写回文件
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=4, ensure_ascii=False)

        print(f"✅ 小地图区域已成功保存: top={self.y}, left={self.x}, size={self.size}")


if __name__ == "__main__":
    root = tk.Tk()
    app = MinimapSelector(root)
    root.mainloop()