"""
输入控制模块 - 基于 Interception 驱动级输入（内核层模拟键鼠，游戏反作弊无法检测）
"""
import os
import sys
import random
import time
import threading
import logging
from pathlib import Path
from typing import Tuple, Optional

logger = logging.getLogger("gameauto.controller")

# Python 3.8+ 限制 DLL 加载路径，需显式添加项目根目录
# interception.dll 位于项目根目录，不在 src/engine/
_project_root = Path(__file__).parent.parent.parent.resolve()
if hasattr(os, "add_dll_directory"):
    os.add_dll_directory(str(_project_root))
    os.add_dll_directory(str(_project_root / "src" / "engine"))

_IMPORT_ERROR_HELP = """
+====================================================+
|  Interception driver not installed or misconfigured |
+====================================================+
|                                                    |
|  This program requires the Interception kernel      |
|  driver to control keyboard and mouse.              |
|                                                    |
|  Installation steps:                                |
|    1. Download driver:                              |
|       github.com/oblitum/Interception/releases      |
|    2. Extract, run cmd as Administrator             |
|    3. Run: install-interception.exe /install        |
|    4. Restart your computer                         |
|                                                    |
|  Verify installation:                               |
|    sc query interception   -> should show RUNNING   |
|                                                    |
|  If driver is installed but still failing:           |
|    -- Run this program as Administrator             |
|    -- Make sure interception.dll is in project root |
|    -- Make sure interception-python is installed    |
|                                                    |
+====================================================+
"""

# 提前检查 interception.dll 是否存在
_dll_path = _project_root / "interception.dll"
if not _dll_path.exists():
    raise RuntimeError(
        f"\n[ERROR] 找不到 interception.dll\n"
        f"   预期位置: {_dll_path}\n"
        f"   请确保 interception.dll 在项目根目录。\n"
        f"{_IMPORT_ERROR_HELP}"
    )

try:
    import interception
except ImportError as e:
    raise ImportError(
        f"\n[ERROR] 无法导入 interception-python 包\n"
        f"   请运行: pip install interception-python\n"
        f"   详细错误: {e}\n"
        f"{_IMPORT_ERROR_HELP}"
    )


class Controller:
    """游戏输入控制器（驱动级，线程安全）"""

    _initialized = False

    def __init__(self, move_speed: float = 1.0):
        self.speed = move_speed
        self._input_lock = threading.Lock()
        if not Controller._initialized:
            try:
                interception.auto_capture_devices()
                Controller._initialized = True
            except Exception as e:
                raise RuntimeError(
                    f"\n[ERROR] Interception 驱动初始化失败！\n\n"
                    f"可能原因：\n"
                    f"  1. 驱动未安装 → 运行 install-interception.exe /install 并重启\n"
                    f"  2. 驱动未运行 → 以管理员身份运行本程序\n"
                    f"  3. 设备被占用 → 关闭其他使用 Interception 的程序\n\n"
                    f"详细错误: {e}\n"
                    f"{_IMPORT_ERROR_HELP}"
                )

    def acquire_lock(self):
        """获取输入锁（用于多线程原子操作）"""
        self._input_lock.acquire()

    def release_lock(self):
        """释放输入锁"""
        self._input_lock.release()

    def __enter__(self):
        self.acquire_lock()
        return self

    def __exit__(self, *args):
        self.release_lock()

    # ---- 鼠标 ----

    def move_to(self, x: int, y: int, human_like: bool = True):
        if human_like:
            self._human_move(x, y)
        else:
            interception.move_to(x, y)

    def click(self, x: Optional[int] = None, y: Optional[int] = None, button: str = "left"):
        if x is not None and y is not None:
            self.move_to(x, y)
            time.sleep(random.uniform(0.03, 0.08))
        interception.click(button=button)

    def mouse_down(self, button: str = "left"):
        interception.mouse_down(button)

    def mouse_up(self, button: str = "left"):
        interception.mouse_up(button)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None):
        self.click(x, y, button="right")

    def scroll(self, amount: int, x: Optional[int] = None, y: Optional[int] = None):
        if x is not None and y is not None:
            self.move_to(x, y)
        direction = "up" if amount > 0 else "down"
        for _ in range(abs(amount)):
            interception.scroll(direction)

    def move_relative(self, dx: int, dy: int = 0):
        """相对移动鼠标（用于转动视角）"""
        interception.move_relative(dx, dy)

    def camera_look(self, dx: int, dy: int = 0):
        """按住右键拖动鼠标转动游戏视角"""
        interception.mouse_down('right')
        time.sleep(random.uniform(0.015, 0.03))
        interception.move_relative(dx, dy)
        time.sleep(random.uniform(0.015, 0.03))
        interception.mouse_up('right')

    @property
    def position(self) -> Tuple[int, int]:
        return interception.mouse_position()

    # ---- 键盘 ----

    def key_down(self, key: str):
        """按下键（不释放）"""
        interception.key_down(key)

    def key_up(self, key: str):
        """释放键"""
        interception.key_up(key)

    def press(self, key: str, duration: float = 0.08):
        """按下并释放一个键"""
        self.key_down(key)
        time.sleep(duration / self.speed)
        self.key_up(key)

    def hotkey(self, *keys):
        """组合键（按住所有修饰键然后按最后一个键）"""
        *mods, main = keys
        for k in mods:
            interception.key_down(k)
        time.sleep(0.03)
        interception.press(main)
        time.sleep(0.03)
        for k in reversed(mods):
            interception.key_up(k)

    def hold_key(self, key: str, duration: float):
        """按住键一段时间"""
        interception.key_down(key)
        time.sleep(duration / self.speed)
        interception.key_up(key)

    def walk(self, direction: str, duration: float = 0.5):
        self.hold_key(direction, duration)

    def type_text(self, text: str, interval: float = 0.05):
        for ch in text:
            interception.press(ch)
            time.sleep(interval / self.speed)

    # ---- 人类化鼠标移动 ----

    def _human_move(self, x: int, y: int):
        try:
            from interception import beziercurve
            params = beziercurve.BezierCurveParams()
            interception.move_to(x, y, params)
        except Exception:
            interception.move_to(x, y)


def emergency_stop_hotkey():
    """注册紧急停止热键（Ctrl+Shift+Q）"""
    from pynput import keyboard

    def on_press(key):
        try:
            if (key == keyboard.KeyCode.from_char('q') and
                    hasattr(on_press, 'ctrl') and on_press.ctrl and on_press.shift):
                logger.info("紧急停止: 用户触发 Ctrl+Shift+Q")
                import sys
                sys.exit(0)
        except AttributeError:
            pass
        try:
            on_press.ctrl = (key == keyboard.Key.ctrl_l or key == keyboard.Key.ctrl_r)
            on_press.shift = (key == keyboard.Key.shift_l or key == keyboard.Key.shift_r)
        except AttributeError:
            on_press.ctrl = False
            on_press.shift = False

    on_press.ctrl = False
    on_press.shift = False

    listener = keyboard.Listener(on_press=on_press, daemon=True)
    listener.start()
    return listener
