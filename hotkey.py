"""
全局热键 — GetAsyncKeyState 主线程轮询
不用 hook，不用注册，不用后台线程
"""
import ctypes
import time
import logging

logger = logging.getLogger("gameauto.hotkey")

user32 = ctypes.windll.user32


class HotkeyBinder:
    """在主线程轮询按键状态"""

    def __init__(self, root):
        self._root = root
        self._entries = []  # [(name, vk, need_ctrl, need_shift, callback)]
        self._cooldowns = {}
        self._polling = False

    def register(self, name: str, key: str, callback, ctrl=False, shift=False):
        vk = _char_to_vk(key)
        self._entries.append((name, vk, ctrl, shift, callback))
        self._cooldowns[name] = 0

    def start(self):
        if self._polling:
            return
        self._polling = True
        names = [e[0] for e in self._entries]
        logger.info(f"主线程轮询已启动, 注册: {names}")
        self._root.after(50, self._poll)  # 延迟 50ms 确保窗口就绪

    def _poll(self):
        if not self._polling:
            return

        try:
            ctrl_down = (user32.GetAsyncKeyState(0x11) & 0x8000) != 0
            shift_down = (user32.GetAsyncKeyState(0x10) & 0x8000) != 0

            for name, vk, need_ctrl, need_shift, cb in self._entries:
                key_down = (user32.GetAsyncKeyState(vk) & 0x8000) != 0
                if key_down and need_ctrl == ctrl_down and need_shift == shift_down:
                    now = time.time()
                    if now - self._cooldowns[name] > 0.5:
                        self._cooldowns[name] = now
                        try:
                            cb()
                        except Exception as e:
                            logger.error(f"{name} 回调错误: {e}")
        except Exception as e:
            logger.error(f"轮询异常: {e}")

        self._root.after(20, self._poll)  # 20ms 轮询，更密集

    def stop(self):
        self._polling = False

    def cleanup(self):
        self.stop()


def _char_to_vk(char: str) -> int:
    mapping = {
        "L": 0x4C, "Q": 0x51, "W": 0x57, "E": 0x45, "R": 0x52, "T": 0x54,
        "A": 0x41, "S": 0x53, "D": 0x44, "F": 0x46, "G": 0x47,
        "Z": 0x5A, "X": 0x58, "C": 0x43, "V": 0x56, "B": 0x42,
        "N": 0x4E, "M": 0x4D, "K": 0x4B, "J": 0x4A, "H": 0x48,
        "U": 0x55, "I": 0x49, "O": 0x4F, "P": 0x50,
        "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34, "5": 0x35,
        "F1": 0x70, "F2": 0x71, "F3": 0x72, "F4": 0x73,
        "F5": 0x74, "F6": 0x75, "F7": 0x76, "F8": 0x77,
        "F9": 0x78, "F10": 0x79, "F11": 0x7A, "F12": 0x7B,
        "SCROLL": 0x91, "PAUSE": 0x13,
    }
    return mapping.get(char.upper(), 0)


def create_hotkey(root, callbacks: dict):
    binder = HotkeyBinder(root)
    for key, data in callbacks.items():
        if isinstance(data, tuple):
            callback, mods = data
            ctrl = "ctrl" in mods
            shift = "shift" in mods
        else:
            callback = data
            ctrl = shift = False
        binder.register(key, key, callback, ctrl=ctrl, shift=shift)
    binder.start()
    return binder
