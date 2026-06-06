"""
MinimapDetector 单元测试 — 验证霍夫圆检测
"""
import sys
from pathlib import Path
import numpy as np
import cv2
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from minimap_detector import MinimapDetector


class TestMinimapDetectorInit:
    """初始化状态"""

    def test_initial_no_cache(self):
        d = MinimapDetector()
        assert d.cached_region is None

    def test_detect_none_frame(self):
        d = MinimapDetector()
        assert d.detect(None) is None

    def test_reset_clears_cache(self):
        d = MinimapDetector()
        d._cached_region = (100, 100, 180, 180)
        d.reset()
        assert d.cached_region is None


class TestDetectOnScreenshots:
    """在真实游戏截图上检测小地图"""

    @pytest.fixture(autouse=True)
    def setup(self):
        img_dir = Path(__file__).parent.parent / "datasets" / "default" / "images" / "train"
        imgs = sorted(img_dir.glob("*.png"))
        if not imgs:
            pytest.skip("No training images found")
        self.imgs = imgs

    def test_detects_minimap_on_first_screenshot(self):
        img = cv2.imread(str(self.imgs[0]))
        assert img is not None

        d = MinimapDetector()
        region = d.detect(img)

        assert region is not None
        x, y, w, h = region
        assert w > 100 and h > 100, f"Region too small: {w}x{h}"
        assert x > 0 and y > 0
        assert x + w <= img.shape[1]
        assert y + h <= img.shape[0]

    def test_detects_consistent_position(self):
        """多张截图检测结果应该一致（±10px）"""
        d = MinimapDetector()
        positions = []

        for img_path in self.imgs[:5]:
            img = cv2.imread(str(img_path))
            if img is None:
                continue
            region = d.detect(img)
            if region:
                positions.append(region)

        assert len(positions) >= 3, "Not enough detections"

        # 所有检测结果应该接近
        xs = [p[0] for p in positions]
        ys = [p[1] for p in positions]
        assert max(xs) - min(xs) < 20, f"X spread too large: {xs}"
        assert max(ys) - min(ys) < 20, f"Y spread too large: {ys}"

    def test_detect_in_top_right(self):
        """小地图应该在屏幕右上角"""
        img = cv2.imread(str(self.imgs[0]))
        h, w = img.shape[:2]

        d = MinimapDetector()
        region = d.detect(img)

        assert region is not None
        rx, ry, rw, rh = region
        # 小地图中心应该在右半部分
        assert rx + rw // 2 > w * 0.6, "Not in right half"
        # 小地图中心应该在上半部分
        assert ry + rh // 2 < h * 0.4, "Not in top half"

    def test_caching_works(self):
        """第二次检测应该使用缓存"""
        img = cv2.imread(str(self.imgs[0]))
        d = MinimapDetector()

        r1 = d.detect(img)
        assert r1 is not None
        assert d.cached_region is not None

        # 第二次应该返回缓存
        r2 = d.detect(img)
        assert r2 == r1

    def test_verify_cached_rejects_blank(self):
        """空白图像验证应该失败"""
        d = MinimapDetector()
        d._cached_region = (100, 100, 180, 180)

        blank = np.zeros((720, 1280, 3), dtype=np.uint8)
        assert d._verify_cached(blank) is False


class TestPickBestCircle:
    """圆候选评分"""

    def test_prefers_top_right(self):
        d = MinimapDetector()
        roi_shape = (400, 640, 3)

        # 两个候选：左下角 vs 右上角
        circles = np.array([
            [100, 300, 80],  # 左下角
            [500, 100, 80],  # 右上角
        ])

        best = d._pick_best_circle(circles, roi_shape, 0, 0)
        assert best is not None
        assert best[0] == 500  # 选右上角的

    def test_prefers_correct_radius(self):
        d = MinimapDetector()
        roi_shape = (400, 640, 3)

        # 两个候选：太大 vs 正好
        circles = np.array([
            [500, 100, 110],  # 太大
            [500, 100, 82],   # 正好
        ])

        best = d._pick_best_circle(circles, roi_shape, 0, 0)
        assert best is not None
        assert best[2] == 82  # 选半径接近 85 的
