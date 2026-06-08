"""
GameAuto Configuration Center
"""
from dataclasses import dataclass
from pathlib import Path
import math


@dataclass
class MiningConfig:
    walk_key: str = 'w'
    max_lost_frames: int = 20
    aim_align_window_px: int = 50
    growth_needed: float = 1.10
    walk_range_px: int = 300
    dead_zone_px: int = 5
    dist_far_ratio: float = 0.03
    dist_close_ratio: float = 0.10
    mine_hold_duration: float = 2.0
    mine_cooldown: float = 6.0
    aim_refine_iters: int = 10
    aim_factor_min: float = 0.55
    aim_decay_scale: float = 80
    turn_scale: float = 0.65
    turn_decay_scale: float = 150
    turn_cap_px: int = 120
    fast_turn_cap: int = 130
    fast_turn_factor: float = 0.60
    locked_match_max_dist: int = 350
    creature_cooldown_frames: int = 15
    creature_dodge_px: int = 400
    obstacle_cooldown_frames: int = 10
    obstacle_dodge_px: int = 500
    obstacle_block_ratio: float = 0.2
    scan_step_px: int = 350
    scan_tick_interval: int = 8
    scan_max_timeout: int = 60
    scan_phase_count: int = 4


@dataclass
class AppConfig:
    project_dir: Path = Path(__file__).parent.parent.parent.resolve()
    models_dir: Path = project_dir / "models"
    datasets_dir: Path = project_dir / "datasets"
    routes_dir: Path = project_dir / "routes"
    maps_dir: Path = project_dir / "maps"
    logs_dir: Path = project_dir / "logs"
    screenshots_dir: Path = project_dir / "screenshots"
    default_model_size: str = "n"
    default_epochs: int = 50
    default_batch: int = 16
    detection_classes: tuple = ("ore", "creature", "obstacle", "character")
    class_names: dict = None

    def __post_init__(self):
        self.models_dir.mkdir(exist_ok=True)
        self.logs_dir.mkdir(exist_ok=True)
        self.screenshots_dir.mkdir(exist_ok=True)
        self.class_names = {"ore": 0, "creature": 1, "obstacle": 2, "character": 3}


@dataclass
class RouteConfig:
    minimap_size: int = 180
    mask_outer_radius: int = 90
    mask_inner_radius: int = 15
    sift_nfeatures: int = 2000
    sift_ratio: float = 0.75
    sift_min_matches: int = 8
    sift_ransac_threshold: float = 5.0
    search_window_size: int = 400
    arrow_crop_size: int = 40
    arrow_hsv_low: tuple = (0, 0, 200)
    arrow_hsv_high: tuple = (180, 40, 255)
    arrow_min_area: int = 30
    color_fallback_threshold: int = 3
    color_histogram_bins: int = 32
    color_search_step: int = 50
    arrive_threshold_px: int = 30
    turn_sensitivity: float = 1.5
    turn_cap_px: int = 150
    turn_dead_zone_deg: float = 5.0
    walk_frame_interval: float = 0.08
    mine_timeout: float = 20.0


@dataclass
class AIConfig:
    model_path: str = "models/heatmap_tracker.pth"
    heatmap_size: int = 64
    sift_radius: int = 200
    sift_ratio: float = 0.85
    sift_min_matches: int = 5


@dataclass
class TeleportConfig:
    anchors: list = None

    def __post_init__(self):
        if self.anchors is None:
            self.anchors = [
                (4121, 3964), (3860, 3802), (3742, 3584), (3651, 3181),
                (4102, 3054), (4427, 3546), (5470, 3768), (5790, 3943),
                (6473, 4435), (6467, 5300), (5798, 5092), (5858, 4807),
                (5348, 4837), (5454, 4505), (4834, 4507), (4472, 5251),
                (4897, 5689), (3832, 5558), (4001, 5051), (4339, 4555),
                (4416, 4456), (3598, 4384), (3006, 4676), (3002, 3950),
                (2442, 3627), (3067, 3080), (2923, 2675), (2102, 2496),
                (1242, 2788), (1689, 3285), (1232, 3666), (1811, 4213),
                (2323, 4374), (2428, 5078), (2612, 5689),
            ]

    def find_nearest(self, x, y):
        best_dist = float('inf')
        best_anchor = None
        for ax, ay in self.anchors:
            d = math.hypot(x - ax, y - ay)
            if d < best_dist:
                best_dist = d
                best_anchor = (ax, ay)
        return best_anchor, best_dist


MINING = MiningConfig()
APP = AppConfig()
ROUTE = RouteConfig()
AI = AIConfig()


# ========== 分辨率自适应 ==========

import ctypes

_REF_W, _REF_H = 1920, 1080  # 参考分辨率

# 默认用系统分辨率（可能被 DPI 缩放误导），后续通过 init_resolution 更正
_SCREEN_W, _SCREEN_H = _REF_W, _REF_H
_INITIALIZED = False

def init_resolution(w: int = None, h: int = None):
    """用游戏截图的真实分辨率初始化缩放（在首次截图后调用）"""
    global _SCREEN_W, _SCREEN_H, _INITIALIZED
    if not _INITIALIZED:
        if w and h:
            _SCREEN_W, _SCREEN_H = w, h
        else:
            try:
                user32 = ctypes.windll.user32
                _SCREEN_W = user32.GetSystemMetrics(0)
                _SCREEN_H = user32.GetSystemMetrics(1)
            except Exception:
                pass
        _INITIALIZED = True

def check_resolution_change():
    """检测分辨率是否变更，变了就清除旧校准文件"""
    import json
    from pathlib import Path
    res_file = APP.project_dir / "resolution.json"
    current = {"w": _SCREEN_W, "h": _SCREEN_H}
    changed = False

    if res_file.exists():
        try:
            with open(res_file, encoding="utf-8") as f:
                saved = json.load(f)
            if saved.get("w") != _SCREEN_W or saved.get("h") != _SCREEN_H:
                changed = True
        except Exception:
            changed = True
    else:
        changed = True  # 首次运行

    if changed:
        # 清除旧校准
        mm_file = APP.project_dir / "minimap_region.json"
        if mm_file.exists():
            mm_file.unlink()
        # 保存新分辨率
        with open(res_file, "w", encoding="utf-8") as f:
            json.dump(current, f)
        import logging
        logging.getLogger("gameauto.config").info(
            f"分辨率变更为 {_SCREEN_W}x{_SCREEN_H}，已重置校准")

    return changed

def scale_x(x: int) -> int:
    """水平坐标缩放"""
    return int(x * _SCREEN_W / _REF_W)

def scale_y(y: int) -> int:
    """垂直坐标缩放"""
    return int(y * _SCREEN_H / _REF_H)

def scale_xy(x: int, y: int) -> tuple:
    """坐标缩放"""
    return scale_x(x), scale_y(y)

def scale_size(s: int) -> int:
    """尺寸缩放（取水平和垂直的均值）"""
    return int(s * (_SCREEN_W + _SCREEN_H) / (_REF_W + _REF_H))

# 当前分辨率常量
CURRENT_W, CURRENT_H = _SCREEN_W, _SCREEN_H
TELEPORT = TeleportConfig()
