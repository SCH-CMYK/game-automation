"""
Automator 单元测试 — 验证采矿状态机核心逻辑
"""
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.automation.automator import Automator
from tests.conftest import MockCapture, MockController, MockVision


class TestAutomatorState:
    """start/stop/pause/resume 状态管理"""

    def test_initial_state(self):
        cap = MockCapture()
        vis = MockVision()
        ctrl = MockController()
        auto = Automator(cap, vis, ctrl)

        assert auto.running is False
        assert auto.paused is False
        assert auto.stats == {"clicks": 0, "detections": 0, "loops": 0}

    def test_start_stop(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        auto.start()
        assert auto.running is True
        auto.stop()
        assert auto.running is False

    def test_pause_resume(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        auto.start()
        auto.pause()
        assert auto.paused is True
        auto.resume()
        assert auto.paused is False

    def test_reset_stats(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        auto.stats["clicks"] = 10
        auto.stats["detections"] = 5
        auto.reset_stats()
        assert auto.stats == {"clicks": 0, "detections": 0, "loops": 0}


class TestCalcTurn:
    """calc_turn 辅助函数"""

    def test_dead_zone(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        dx, dy = 3, 2  # < DEAD_ZONE (5)
        result = Automator.calc_turn(dx, dy)
        # 死区内不转向，直接返回 0
        assert result == (0, 0)

    def test_normal_turn(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        # dx=100, DY=0 → 应返回正 x, 0 y
        turn_x, turn_y = Automator.calc_turn(100, 0)
        assert turn_x > 0, f"Expected positive turn_x, got {turn_x}"
        assert turn_y == 0

    def test_turn_capped(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        # 超大距离 → turn 不应超过 cap (120)
        turn_x, turn_y = Automator.calc_turn(500, 0)
        assert abs(turn_x) <= 120, f"Turn_x {turn_x} exceeds cap 120"
        assert abs(turn_y) <= 120

    def test_center_no_turn(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        # 矿石在画面中心 → 不转向
        turn_x, turn_y = Automator.calc_turn(0, 0)
        assert turn_x == 0 and turn_y == 0


class TestMatchLocked:
    """锁定目标匹配"""

    def test_exact_match(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        dets = [{"center": (100, 200), "bbox": (90, 190, 110, 210), "area": 400}]
        result = Automator.match_locked(dets, (100, 200))
        assert result is not None
        assert result["center"] == (100, 200)

    def test_near_match(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        dets = [
            {"center": (500, 500), "bbox": (490, 490, 510, 510), "area": 400},
            {"center": (105, 205), "bbox": (95, 195, 115, 215), "area": 400},
        ]
        result = Automator.match_locked(dets, (100, 200))
        assert result is not None
        assert result["center"] == (105, 205)

    def test_no_match_too_far(self):
        auto = Automator(MockCapture(), MockVision(), MockController())
        dets = [{"center": (900, 900), "bbox": (890, 890, 910, 910), "area": 400}]
        result = Automator.match_locked(dets, (100, 200), max_dist=350)
        assert result is None


class TestWalkToMine:
    """采矿主循环（截断测试，只验证前几帧）"""

    def test_stops_when_not_running(self):
        cap = MockCapture()
        vis = MockVision()
        ctrl = MockController()
        auto = Automator(cap, vis, ctrl)

        auto.running = False
        auto.walk_to_mine()
        # 不应该有按键调用
        assert len(ctrl.calls) == 0

    def test_detection_increments_count(self):
        cap = MockCapture()
        vis = MockVision()
        ctrl = MockController()
        auto = Automator(cap, vis, ctrl)

        # 启动后立即停止（只运行一次循环）
        auto.start()
        # 在 walk_to_mine 运行一次后停止
        import threading
        stop_timer = threading.Timer(0.3, auto.stop)
        stop_timer.start()

        auto.walk_to_mine()
        assert auto.stats["detections"] >= 1

    def test_creature_avoids(self):
        cap = MockCapture()
        vis = MockVision()
        ctrl = MockController()
        auto = Automator(cap, vis, ctrl)

        # 精灵在画面中心
        vis.set_creature([{
            "bbox": (600, 340, 680, 380),
            "center": (640, 360),
            "confidence": 0.85,
            "class": "creature",
            "area": 3200,
        }])

        auto.start()
        import threading
        stop_timer = threading.Timer(0.3, auto.stop)
        stop_timer.start()

        auto.walk_to_mine()

        # 应该有一次 move_relative（闪避）
        moves = [c for c in ctrl.calls if c[0] == 'move_relative']
        assert len(moves) >= 1, "没有闪避移动"

    def test_obstacle_blocks(self):
        cap = MockCapture()
        vis = MockVision()
        ctrl = MockController()
        auto = Automator(cap, vis, ctrl)

        # 矿石 + 障碍物同时存在
        vis.set_ore([{"bbox": (600, 340, 680, 380), "center": (640, 360),
                       "confidence": 0.9, "class": "ore", "area": 1200}])
        vis.set_obstacle([{
            "bbox": (600, 340, 680, 380),
            "center": (640, 360),
            "confidence": 0.8,
            "class": "obstacle",
            "area": 3200,
        }])

        auto.start()
        import threading
        stop_timer = threading.Timer(0.3, auto.stop)
        stop_timer.start()

        auto.walk_to_mine()

        # 应该有闪避移动
        moves = [c for c in ctrl.calls if c[0] == 'move_relative']
        assert len(moves) >= 1, "没有障碍物闪避"
