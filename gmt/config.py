import json
import os
import sys

# ==========================================
# 核心黑科技：兼容 PyInstaller 打包后的路径寻找
# ==========================================
if getattr(sys, 'frozen', False):
    # 如果是打包后的 .exe 运行，去 exe 所在的同级目录找配置文件
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # 如果是在代码编辑器里直接运行 main.py，去当前代码所在的目录找
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# ==========================================
# 默认配置字典 (如果 JSON 文件丢失，用来兜底并重新生成)
# ==========================================
DEFAULT_CONFIG = {
    "MINIMAP": {"top": 292, "left": 1853, "width": 150, "height": 150},
    "WINDOW_GEOMETRY": "400x400+1500+100",
    "VIEW_SIZE": 400,
    "LOGIC_MAP_PATH": "big_map.png",
    "DISPLAY_MAP_PATH": "big_map-1.png",
    "MAX_LOST_FRAMES": 50,

    "SIFT_REFRESH_RATE": 50,
    "SIFT_CLAHE_LIMIT": 3.0,
    "SIFT_MATCH_RATIO": 0.9,
    "SIFT_MIN_MATCH_COUNT": 5,
    "SIFT_RANSAC_THRESHOLD": 8.0,

    "AI_REFRESH_RATE": 200,
    "AI_CONFIDENCE_THRESHOLD": 0.6,
    "AI_MIN_MATCH_COUNT": 6,
    "AI_RANSAC_THRESHOLD": 8.0,
    "AI_SCAN_SIZE": 1600,
    "AI_SCAN_STEP": 1400,
    "AI_TRACK_RADIUS": 500
}


def load_config():
    """读取 JSON 配置文件，如果没有则自动生成"""
    if not os.path.exists(CONFIG_FILE):
        print("未找到 config.json，正在自动生成默认配置文件...")
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"生成配置文件失败: {e}")
        return DEFAULT_CONFIG

    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            user_config = json.load(f)

            # 巧妙的合并逻辑：防止用户在 JSON 里少填了某个字段导致程序崩溃
            merged_config = DEFAULT_CONFIG.copy()
            merged_config.update(user_config)
            return merged_config
    except Exception as e:
        print(f"⚠️ 读取 config.json 失败 (格式错误?)，将临时使用默认配置！错误: {e}")
        return DEFAULT_CONFIG


# ==========================================
# 加载配置并导出变量 (让 main.py 可以直接 import 这些变量)
# ==========================================
settings = load_config()

# 通用设置
MINIMAP = settings.get("MINIMAP")
WINDOW_GEOMETRY = settings.get("WINDOW_GEOMETRY")
VIEW_SIZE = settings.get("VIEW_SIZE")
LOGIC_MAP_PATH = settings.get("LOGIC_MAP_PATH")
DISPLAY_MAP_PATH = settings.get("DISPLAY_MAP_PATH")
MAX_LOST_FRAMES = settings.get("MAX_LOST_FRAMES")

# SIFT 专属
SIFT_REFRESH_RATE = settings.get("SIFT_REFRESH_RATE")
SIFT_CLAHE_LIMIT = settings.get("SIFT_CLAHE_LIMIT")
SIFT_MATCH_RATIO = settings.get("SIFT_MATCH_RATIO")
SIFT_MIN_MATCH_COUNT = settings.get("SIFT_MIN_MATCH_COUNT")
SIFT_RANSAC_THRESHOLD = settings.get("SIFT_RANSAC_THRESHOLD")

# AI 专属
AI_REFRESH_RATE = settings.get("AI_REFRESH_RATE")
AI_CONFIDENCE_THRESHOLD = settings.get("AI_CONFIDENCE_THRESHOLD")
AI_MIN_MATCH_COUNT = settings.get("AI_MIN_MATCH_COUNT")
AI_RANSAC_THRESHOLD = settings.get("AI_RANSAC_THRESHOLD")
AI_SCAN_SIZE = settings.get("AI_SCAN_SIZE")
AI_SCAN_STEP = settings.get("AI_SCAN_STEP")
AI_TRACK_RADIUS = settings.get("AI_TRACK_RADIUS")