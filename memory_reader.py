"""
游戏内存读取器 — 直接读取角色坐标

使用方法：
1. 用 Cheat Engine 找到角色坐标地址
2. 在 config.json 里配置地址
3. 运行程序自动读取

原理：Win32 ReadProcessMemory API
"""
import ctypes
import ctypes.wintypes as wintypes
import json
import logging
from pathlib import Path

logger = logging.getLogger("gameauto.memory")

# Win32 API
kernel32 = ctypes.windll.kernel32

PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400


class MemoryReader:
    """游戏内存读取器"""

    def __init__(self, process_name=None, config_file=None):
        self._handle = None
        self._base_addr = 0
        self._offsets = {}
        self._process_name = process_name or "Game.exe"

        if config_file:
            self._load_config(config_file)

    def _load_config(self, config_file):
        """加载地址配置"""
        path = Path(config_file)
        if path.exists():
            with open(path) as f:
                config = json.load(f)
            self._base_addr = config.get("base_address", 0)
            self._offsets = config.get("offsets", {})
            logger.info(f"加载配置: base=0x{self._base_addr:X}")

    def connect(self, process_name=None):
        """连接到游戏进程"""
        name = process_name or self._process_name

        # 查找进程 PID
        pid = self._find_process(name)
        if pid is None:
            logger.error(f"找不到进程: {name}")
            return False

        # 打开进程
        self._handle = kernel32.OpenProcess(
            PROCESS_VM_READ | PROCESS_QUERY_INFORMATION,
            False,
            pid
        )

        if not self._handle:
            logger.error(f"无法打开进程 (需要管理员权限)")
            return False

        logger.info(f"已连接进程: {name} (PID: {pid})")
        return True

    def _find_process(self, name):
        """查找进程 PID"""
        import subprocess
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {name}", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n'):
                if name.lower() in line.lower():
                    parts = line.split(',')
                    if len(parts) >= 2:
                        return int(parts[1].strip('"'))
        except Exception:
            pass
        return None

    def read_float(self, address):
        """读取浮点数"""
        if not self._handle:
            return None

        buffer = ctypes.c_float()
        bytes_read = ctypes.c_size_t(0)

        success = kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            ctypes.byref(buffer),
            ctypes.sizeof(buffer),
            ctypes.byref(bytes_read)
        )

        if success and bytes_read.value == ctypes.sizeof(buffer):
            return buffer.value
        return None

    def read_int(self, address):
        """读取整数"""
        if not self._handle:
            return None

        buffer = ctypes.c_int32()
        bytes_read = ctypes.c_size_t(0)

        success = kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            ctypes.byref(buffer),
            ctypes.sizeof(buffer),
            ctypes.byref(bytes_read)
        )

        if success and bytes_read.value == ctypes.sizeof(buffer):
            return buffer.value
        return None

    def read_double(self, address):
        """读取双精度浮点数"""
        if not self._handle:
            return None

        buffer = ctypes.c_double()
        bytes_read = ctypes.c_size_t(0)

        success = kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            ctypes.byref(buffer),
            ctypes.sizeof(buffer),
            ctypes.byref(bytes_read)
        )

        if success and bytes_read.value == ctypes.sizeof(buffer):
            return buffer.value
        return None

    def read_bytes(self, address, size):
        """读取字节数组"""
        if not self._handle:
            return None

        buffer = (ctypes.c_uint8 * size)()
        bytes_read = ctypes.c_size_t(0)

        success = kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            buffer,
            size,
            ctypes.byref(bytes_read)
        )

        if success:
            return bytes(buffer[:bytes_read.value])
        return None

    def read_string(self, address, length=64):
        """读取字符串"""
        data = self.read_bytes(address, length)
        if data:
            # 找到 null 终止符
            null_idx = data.find(b'\x00')
            if null_idx >= 0:
                data = data[:null_idx]
            try:
                return data.decode('utf-8', errors='replace')
            except Exception:
                return data.hex()
        return None

    def read_pointer(self, address):
        """读取指针（64位）"""
        if not self._handle:
            return None

        buffer = ctypes.c_uint64()
        bytes_read = ctypes.c_size_t(0)

        success = kernel32.ReadProcessMemory(
            self._handle,
            ctypes.c_void_p(address),
            ctypes.byref(buffer),
            ctypes.sizeof(buffer),
            ctypes.byref(bytes_read)
        )

        if success and bytes_read.value == ctypes.sizeof(buffer):
            return buffer.value
        return None

    def read_with_offsets(self, base, offsets, read_func=None):
        """通过指针链读取值

        Args:
            base: 基地址
            offsets: 偏移量列表
            read_func: 最终读取函数（默认 read_float）

        Returns:
            读取到的值，或 None
        """
        if read_func is None:
            read_func = self.read_float

        addr = base
        for offset in offsets[:-1]:
            ptr = self.read_pointer(addr)
            if ptr is None:
                return None
            addr = ptr + offset

        # 最后一层
        if offsets:
            addr += offsets[-1]

        return read_func(addr)

    def get_position(self):
        """读取角色坐标

        Returns:
            (x, y, z) 或 None
        """
        if "position" not in self._offsets:
            return None

        pos_config = self._offsets["position"]
        base = pos_config.get("base", self._base_addr)
        offsets = pos_config.get("offsets", [])
        data_type = pos_config.get("type", "float")

        read_func = {"float": self.read_float, "double": self.read_double}.get(
            data_type, self.read_float)

        if offsets:
            # 指针链
            x = self.read_with_offsets(base, offsets + [0], read_func)
            y = self.read_with_offsets(base, offsets + [4], read_func)
            z = self.read_with_offsets(base, offsets + [8], read_func)
        else:
            # 直接地址
            x = read_func(base)
            y = read_func(base + 4)
            z = read_func(base + 8)

        if x is not None and y is not None:
            return (x, y, z)

        return None

    def disconnect(self):
        """断开连接"""
        if self._handle:
            kernel32.CloseHandle(self._handle)
            self._handle = None
            logger.info("已断开进程连接")

    def __del__(self):
        self.disconnect()


def create_sample_config():
    """创建示例配置文件"""
    config = {
        "_说明": "用 Cheat Engine 找到角色坐标地址后填入",
        "_步骤": [
            "1. 打开 Cheat Engine，附加到游戏进程",
            "2. 搜索角色 X 坐标（float 类型）",
            "3. 在游戏里左右移动",
            "4. 再次搜索变化后的值",
            "5. 重复直到找到稳定地址",
            "6. 把地址填入下面的 base_address",
            "7. 如果是多级指针，填入 offsets"
        ],
        "process_name": "Game.exe",
        "base_address": 0,
        "offsets": {
            "position": {
                "_说明": "角色 X/Y/Z 坐标",
                "base": 0,
                "offsets": [0x0],
                "type": "float"
            }
        }
    }

    config_path = Path(__file__).parent / "memory_config.json"
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"配置文件已创建: {config_path}")
    print("请用 Cheat Engine 找到地址后编辑此文件")


if __name__ == "__main__":
    import sys

    if "--init" in sys.argv:
        create_sample_config()
    else:
        # 测试连接
        config_path = Path(__file__).parent / "memory_config.json"
        reader = MemoryReader(config_file=config_path)

        if reader.connect():
            print("连接成功！")
            pos = reader.get_position()
            if pos:
                print(f"角色位置: x={pos[0]:.1f}, y={pos[1]:.1f}, z={pos[2]:.1f}")
            else:
                print("无法读取坐标（请检查 memory_config.json 中的地址）")
            reader.disconnect()
        else:
            print("连接失败（需要管理员权限 + 游戏正在运行）")
