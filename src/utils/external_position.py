"""
外部定位读取器 — 从 AIMapTracker 窗口标题读取玩家坐标

用户手动运行 AIMapTracker.exe，我们读取它的窗口标题获取坐标。
不启动子进程，不干扰游戏。
"""
import re
import time
import logging
import ctypes
from ctypes import wintypes

logger = logging.getLogger("gameauto.external_pos")

user32 = ctypes.windll.user32
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible


def _parse_coordinates(line):
    """从输出行中提取坐标

    支持格式：
    - "X=3009.4, Y=4824.4"
    - "x=3009 y=4824"
    - "(3009, 4824)"
    - "Position: 3009, 4824"
    - "SIFT 定位成功: X=3009.4, Y=4824.4"
    """
    # 格式 1: X=3009.4, Y=4824.4
    m = re.search(r'[Xx]\s*[=:]\s*([\d.]+)\s*[,;]?\s*[Yy]\s*[=:]\s*([\d.]+)', line)
    if m:
        return float(m.group(1)), float(m.group(2))

    # 格式 2: (3009, 4824) 或 [3009, 4824]
    m = re.search(r'[\(\[]\s*([\d.]+)\s*,\s*([\d.]+)\s*[\)\]]', line)
    if m:
        return float(m.group(1)), float(m.group(2))

    return None


class ExternalPositioner:
    """从 AIMapTracker 子进程读取位置"""

    def __init__(self, exe_path=None):
        self._last_pos = None
        self._process = None
        self._thread = None
        self._running = False

        # 查找 AIMapTracker.exe
        if exe_path:
            self._exe_path = Path(exe_path)
        else:
            # 默认路径
            self._exe_path = Path(r"D:\6.3\N卡用户_AIMapTracker6.3\N卡用户_AIMapTracker6.3\AIMapTracker.exe")

        if not self._exe_path.exists():
            logger.warning(f"AIMapTracker 未找到: {self._exe_path}")

    def start(self):
        """启动 AIMapTracker 子进程"""
        if not self._exe_path.exists():
            return False

        if self._process and self._process.poll() is None:
            logger.info("AIMapTracker 已在运行")
            return True

        try:
            # 启动 AIMapTracker（隐藏窗口，不干扰游戏）
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

            # 设置 UTF-8 编码（AIMapTracker 输出含 emoji，GBK 不支持）
            import os
            env = os.environ.copy()
            env["PYTHONIOENCODING"] = "utf-8"

            self._process = subprocess.Popen(
                [str(self._exe_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                cwd=str(self._exe_path.parent),
                startupinfo=startupinfo,
                env=env,
            )
            self._running = True

            # 等一下让窗口创建，然后强制隐藏
            time.sleep(0.5)
            try:
                # 隐藏所有 AIMapTracker 相关窗口
                self._hide_aimaptracker_windows()
            except Exception:
                pass

            # 后台线程读取 stdout
            self._thread = threading.Thread(target=self._read_output, daemon=True)
            self._thread.start()

            # 后台线程读取 stderr
            self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
            self._stderr_thread.start()

            logger.info(f"AIMapTracker 已启动 (PID: {self._process.pid}, 后台运行)")
            return True
        except Exception as e:
            logger.error(f"启动 AIMapTracker 失败: {e}")
            return False

    def _read_output(self):
        """后台线程：持续读取 AIMapTracker stdout"""
        while self._running and self._process and self._process.poll() is None:
            try:
                line = self._process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    logger.info(f"[AIMapTracker] {line}")
                    pos = _parse_coordinates(line)
                    if pos:
                        self._last_pos = pos
                        logger.info(f"外部定位: ({pos[0]:.1f}, {pos[1]:.1f})")
            except Exception:
                break
        exit_code = self._process.poll() if self._process else None
        logger.info(f"AIMapTracker stdout 结束 (exit={exit_code})")
        self._running = False

    def _read_stderr(self):
        """后台线程：读取 AIMapTracker stderr"""
        while self._running and self._process and self._process.poll() is None:
            try:
                line = self._process.stderr.readline()
                if not line:
                    break
                line = line.strip()
                if line:
                    logger.warning(f"[AIMapTracker stderr] {line}")
            except Exception:
                break

    def _hide_aimaptracker_windows(self):
        """隐藏 AIMapTracker 的所有窗口（不干扰游戏）"""
        import ctypes
        from ctypes import wintypes

        EnumWindows = user32.EnumWindows
        GetWindowTextW = user32.GetWindowTextW
        GetWindowTextLengthW = user32.GetWindowTextLengthW
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId
        IsWindowVisible = user32.IsWindowVisible

        pid = self._process.pid
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

        def callback(hwnd, _):
            if IsWindowVisible(hwnd):
                # 检查是否是 AIMapTracker 的窗口
                wpid = wintypes.DWORD()
                GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
                if wpid.value == pid:
                    ShowWindow(hwnd, SW_HIDE)
                    logger.debug(f"隐藏窗口 PID={pid}")
                else:
                    # 也检查窗口标题
                    length = GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value
                        if "aimaptracker" in title.lower() or "maptracker" in title.lower():
                            ShowWindow(hwnd, SW_HIDE)
                            logger.debug(f"隐藏窗口: {title}")
            return True

        EnumWindows(EnumWindowsProc(callback), 0)

    def get_position(self):
        """获取玩家位置

        Returns:
            (x, y) 大地图坐标，或 None
        """
        return self._last_pos

    def stop(self):
        """停止 AIMapTracker"""
        self._running = False
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()
            logger.info("AIMapTracker 已停止")

    @property
    def is_available(self):
        """AIMapTracker 是否在运行"""
        return self._process is not None and self._process.poll() is None

    @property
    def is_running(self):
        return self._running


if __name__ == "__main__":
    print("Looking for AIMapTracker window...")
    ep = ExternalPositioner()

    for i in range(20):
        title = ep.get_window_title()
        pos = ep.get_position()
        if title:
            print(f"Title: {title}")
            print(f"Position: {pos}")
        else:
            print("Not found")
        time.sleep(1)
