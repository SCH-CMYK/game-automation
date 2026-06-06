"""
冒烟测试 — 验证项目关键路径，无需 GPU/游戏即可运行

用法:
    python tests/smoke_test.py
    pytest tests/smoke_test.py -v
"""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_imports():
    """所有核心模块可正常导入"""
    from src.engine.screen_capture import ScreenCapture
    from src.engine.vision_engine import VisionEngine
    from src.engine.controller import Controller
    from src.automation.automator import Automator
    from src.automation.hotkey import HotkeyBinder, create_hotkey
    from src.automation.route_planner import RoutePlanner
    from src.training.trainer import YOLOTrainer, create_dataset_structure
    from src.utils.sift_config import MINIMAP, SIFT_MATCH_RATIO
    from src.utils.config import MINING, APP
    from src.utils.logger import get_logger
    import interception
    import yaml
    print("  PASS: imports")


def test_config():
    """配置正常加载"""
    from src.utils.config import MINING, APP

    assert hasattr(MINING, 'walk_key'), "MiningConfig missing walk_key"
    assert MINING.max_lost_frames == 20
    assert MINING.mine_hold_duration == 2.0

    assert APP.project_dir.exists(), "APP.project_dir does not exist"
    assert APP.models_dir.exists(), "APP.models_dir does not exist"
    print("  PASS: config")


def test_route_formats():
    """所有路线 JSON 文件格式正确"""
    routes_dir = Path(__file__).parent.parent / "routes"
    count = 0
    bad = []

    for f in sorted(routes_dir.glob("**/*.json")):
        count += 1
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        # 兼容两种格式
        has_waypoints = "waypoints" in data
        has_points = "points" in data
        if not has_waypoints and not has_points:
            bad.append(str(f.relative_to(routes_dir)))

    assert len(bad) == 0, f"无法识别的格式: {bad}"
    print(f"  PASS: {count} routes parsed OK")


def test_data_yaml():
    """data.yaml 结构正确"""
    import yaml
    yaml_path = Path(__file__).parent.parent / "datasets" / "default" / "data.yaml"

    assert yaml_path.exists(), "data.yaml not found"
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data['nc'] == 4, f"Expected nc=4, got {data['nc']}"
    assert len(data['names']) == 4, f"Expected 4 names, got {len(data['names'])}"
    print("  PASS: data.yaml")


def test_models_exist():
    """至少有一个 .pt 模型文件"""
    models_dir = Path(__file__).parent.parent / "models"
    models = list(models_dir.glob("*.pt"))

    assert len(models) > 0, "没有找到 .pt 模型文件"
    print(f"  PASS: {len(models)} models available")


if __name__ == "__main__":
    print("GameAuto Smoke Test\n")
    results = []
    for name, fn in [
        ("imports", test_imports),
        ("config", test_config),
        ("route_formats", test_route_formats),
        ("data_yaml", test_data_yaml),
        ("models_exist", test_models_exist),
    ]:
        try:
            fn()
            results.append((name, "PASS"))
        except Exception as e:
            results.append((name, f"FAIL: {e}"))

    passed = sum(1 for _, r in results if r == "PASS")
    failed = sum(1 for _, r in results if r != "PASS")
    print(f"\n{passed}/{len(results)} passed, {failed} failed")

    for name, result in results:
        if result != "PASS":
            print(f"  FAIL: {name} — {result}")

    sys.exit(1 if failed else 0)
