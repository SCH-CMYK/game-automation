"""SIFT 匹配参数（加载自 gmt/config.json，此为权威配置源）"""
import json
from pathlib import Path

# 从 GMT 配置加载（权威源）
_gmt_cfg_path = Path(__file__).parent / "gmt" / "config.json"
if _gmt_cfg_path.exists():
    with open(_gmt_cfg_path, encoding="utf-8") as f:
        _gmt = json.load(f)
else:
    _gmt = {}

SIFT_MATCH_RATIO = _gmt.get("SIFT_MATCH_RATIO", 0.9)
SIFT_MIN_MATCH_COUNT = _gmt.get("SIFT_MIN_MATCH_COUNT", 5)
SIFT_RANSAC_THRESHOLD = _gmt.get("SIFT_RANSAC_THRESHOLD", 8.0)
SIFT_CLAHE_LIMIT = _gmt.get("SIFT_CLAHE_LIMIT", 3.0)
MAX_LOST_FRAMES = _gmt.get("MAX_LOST_FRAMES", 50)

# 地图路径（优先用 GMT 的图）
LOGIC_MAP_PATH = _gmt.get("LOGIC_MAP_PATH", "big_map.png")
DISPLAY_MAP_PATH = _gmt.get("DISPLAY_MAP_PATH", "big_map-1.png")
# 小地图区域：霍夫圆自动检测结果（1920x1080 分辨率）
# 注意：gmt/config.json 中的旧值 (top=309, left=1837) 是错误的，实际位置在顶部
# 推荐使用 minimap_detector.py 自动检测，此值仅作为手动回退
MINIMAP = _gmt.get("MINIMAP", {"top": 47, "left": 1724, "width": 162, "height": 162})
