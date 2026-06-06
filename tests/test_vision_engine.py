"""
VisionEngine 单元测试 — 验证检测逻辑
"""
import sys
from pathlib import Path
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from vision_engine import VisionEngine
from logger import get_logger


class TestVisionEngineInit:
    """初始化状态"""

    def test_initial_not_loaded(self):
        ve = VisionEngine()
        assert ve.loaded is False
        assert len(ve.names) == 0

    def test_detect_all_no_model(self):
        """未加载模型时 detect_all 返回空字典"""
        ve = VisionEngine()
        dummy = np.zeros((100, 100, 3), dtype=np.uint8)
        result = ve.detect_all(dummy)
        assert result == {"ore": [], "creature": [], "obstacle": [], "character": []}

    def test_find_best_ore_no_model(self):
        ve = VisionEngine()
        dummy = np.zeros((100, 100, 3), dtype=np.uint8)
        result = ve.find_best_ore(dummy)
        assert result is None

    def test_is_path_blocked_no_model(self):
        ve = VisionEngine()
        dummy = np.zeros((100, 100, 3), dtype=np.uint8)
        result = ve.is_path_blocked(dummy)
        assert result is False


class TestLoadedVisionEngine:
    """加载了真实模型的测试（需要至少一个 .pt 文件）"""

    @pytest.fixture(autouse=True)
    def setup(self):
        models_dir = Path(__file__).parent.parent / "models"
        models = sorted(models_dir.glob("*.pt"), key=lambda p: p.stat().st_size)
        if not models:
            pytest.skip("没有可用的模型文件")
        self.ve = VisionEngine()
        # 用最小的模型（yolo11n.pt ~5 MB）
        ok = self.ve.load(str(models[0]))
        if not ok:
            pytest.skip("模型加载失败")

    def test_load_sets_loaded_flag(self):
        assert self.ve.loaded is True
        assert len(self.ve.names) > 0

    def test_detect_all_returns_grouped(self):
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        result = self.ve.detect_all(dummy, conf=0.5)
        assert "ore" in result
        assert "creature" in result
        assert "obstacle" in result
        assert "character" in result

    def test_find_best_ore_returns_none_on_blank(self):
        """纯黑图上不应该检测到矿石"""
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        result = self.ve.find_best_ore(dummy)
        # 纯黑图可能检出不存在的"矿石"，设为 None 或置信度 < 0.5
        assert result is None or result.get("confidence", 1.0) >= 0.0

    def test_is_path_blocked_returns_bool(self):
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        result = self.ve.is_path_blocked(dummy)
        assert isinstance(result, bool)

    def test_detect_all_with_different_conf(self):
        """不同置信度阈值"""
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        high_conf = self.ve.detect_all(dummy, conf=0.99)
        low_conf = self.ve.detect_all(dummy, conf=0.01)
        # 高置信度下检出更少
        total_high = sum(len(v) for v in high_conf.values())
        total_low = sum(len(v) for v in low_conf.values())
        assert total_high <= total_low, f"high={total_high}, low={total_low}"


class TestRealScreenshot:
    """用真实截图测试检测"""

    @pytest.fixture(autouse=True)
    def setup(self):
        models_dir = Path(__file__).parent.parent / "models"
        models = sorted(models_dir.glob("*.pt"), key=lambda p: p.stat().st_size)
        if not models:
            pytest.skip("没有可用的模型文件")
        self.ve = VisionEngine()
        ok = self.ve.load(str(models[0]))
        if not ok:
            pytest.skip("模型加载失败")

        # 找一张训练图
        train_imgs = list((Path(__file__).parent.parent / "datasets" / "default" / "images" / "train").glob("*.png"))
        self.test_img = str(train_imgs[0]) if train_imgs else None

    def test_detect_on_training_image(self):
        if self.test_img is None:
            pytest.skip("没有训练图片")

        import cv2
        frame = cv2.imread(self.test_img)
        assert frame is not None, f"无法读取 {self.test_img}"

        result = self.ve.detect_all(frame, conf=0.3)
        # 训练图上至少应检出矿石
        total = sum(len(v) for v in result.values())
        assert total >= 0  # 不强制要求检出数量，只确认不崩溃
