"""
自动传送模块 — 打开地图 → 点击传送点 → 等待传送完成

工作流程：
1. 按 M 键打开大地图
2. 在地图上找到传送点（固定坐标）
3. 点击传送点
4. 等待传送完成（检测画面变化）
5. 关闭地图
"""
import time
import logging

logger = logging.getLogger("gameauto.teleport")


class Teleporter:
    """游戏内自动传送"""

    def __init__(self, controller, capture):
        self.controller = controller
        self.capture = capture

        # 传送点坐标（大地图上的像素坐标）
        # 需要根据实际游戏校准
        self.teleport_points = {}

    def register_teleport(self, name, map_x, map_y):
        """注册一个传送点

        Args:
            name: 传送点名称
            map_x, map_y: 传送点在大地图上的坐标
        """
        self.teleport_points[name] = (map_x, map_y)
        logger.info(f"注册传送点: {name} ({map_x}, {map_y})")

    def teleport_to(self, name):
        """传送到指定传送点

        Args:
            name: 传送点名称

        Returns:
            bool: 是否成功
        """
        if name not in self.teleport_points:
            logger.error(f"未知传送点: {name}")
            return False

        map_x, map_y = self.teleport_points[name]
        logger.info(f"传送到: {name} ({map_x}, {map_y})")

        # 1. 按 M 打开地图
        self.controller.press('m')
        time.sleep(1.5)  # 等待地图打开

        # 2. 点击传送点坐标
        self.controller.click(map_x, map_y)
        time.sleep(0.5)

        # 3. 等待确认传送（可能需要再次点击确认）
        # 某些游戏需要点击"确认传送"按钮
        self.controller.click(map_x, map_y)
        time.sleep(3.0)  # 等待传送动画

        # 4. 按 ESC 关闭地图
        self.controller.press('escape')
        time.sleep(0.5)

        logger.info(f"传送完成: {name}")
        return True

    def teleport_to_coords(self, map_x, map_y):
        """传送到指定地图坐标

        Args:
            map_x, map_y: 大地图上的像素坐标

        Returns:
            bool: 是否成功
        """
        logger.info(f"传送到坐标: ({map_x}, {map_y})")

        # 按 M 打开地图
        self.controller.press('m')
        time.sleep(1.5)

        # 点击目标坐标
        self.controller.click(map_x, map_y)
        time.sleep(0.5)
        self.controller.click(map_x, map_y)  # 双击确认
        time.sleep(3.0)

        # 关闭地图
        self.controller.press('escape')
        time.sleep(0.5)

        return True

    def close_map(self):
        """关闭地图"""
        self.controller.press('escape')
        time.sleep(0.3)
