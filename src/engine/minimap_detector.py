"""
小地图自动检测器 — 霍夫圆检测

自动在游戏截图上找到小地图的圆形边框，返回裁剪坐标。
检测结果会缓存，后续帧只做验证（快速），失败时重新检测（完整）。

用法:
    detector = MinimapDetector()
    region = detector.detect(frame)  # (x, y, w, h)
    minimap = frame[y:y+h, x:x+w]
"""
import cv2
import numpy as np
import logging

logger = logging.getLogger("gameauto.minimap")


class MinimapDetector:
    """基于霍夫圆检测的自动小地图定位"""

    def __init__(self):
        from src.utils.config import scale_size
        # 检测参数（按分辨率缩放）
        self._dp = 1.2
        self._min_dist = scale_size(150)
        self._param1 = 100
        self._param2 = 25
        self._min_radius = scale_size(40)
        self._max_radius = scale_size(130)
        self._target_r = scale_size(85)  # expected minimap radius (scaled)

        # 搜索区域（小地图一般在右上角 1/3）
        self._roi_top_ratio = 0.0
        self._roi_bottom_ratio = 0.4
        self._roi_left_ratio = 0.5

        # 缓存
        self._cached_region = None   # (x, y, w, h) 上次检测结果
        self._cache_fail_count = 0   # 缓存验证失败次数
        self._max_cache_fails = 10   # 允许连续失败次数

    def detect(self, frame):
        """Detect minimap position on frame.

        Args:
            frame: BGR screenshot (numpy array)

        Returns:
            (x, y, w, h) region, or None if not found
        """
        if frame is None:
            return None

        h, w = frame.shape[:2]

        # 优先验证缓存位置（快速）
        if self._cached_region is not None:
            if self._verify_cached(frame):
                return self._cached_region
            self._cache_fail_count += 1
            if self._cache_fail_count < self._max_cache_fails:
                return self._cached_region  # 容忍几帧失败

        # 完整检测
        region = self._detect_full(frame)
        if region is not None:
            self._cached_region = region
            self._cache_fail_count = 0
            return region

        return self._cached_region  # 最后回退到缓存

    def _detect_full(self, frame):
        """完整霍夫圆检测（在右上角 ROI 区域）"""
        h, w = frame.shape[:2]

        # 裁剪 ROI（右上角）
        y1 = int(h * self._roi_top_ratio)
        y2 = int(h * self._roi_bottom_ratio)
        x1 = int(w * self._roi_left_ratio)
        roi = frame[y1:y2, x1:w]

        # 灰度 + 模糊
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (9, 9), 2)

        # 霍夫圆检测
        circles = cv2.HoughCircles(
            blurred,
            cv2.HOUGH_GRADIENT,
            dp=self._dp,
            minDist=self._min_dist,
            param1=self._param1,
            param2=self._param2,
            minRadius=self._min_radius,
            maxRadius=self._max_radius,
        )

        if circles is None:
            return None

        circles = np.uint16(np.around(circles))

        # 在检测到的圆中选最佳候选
        best = self._pick_best_circle(circles[0], roi.shape, x1, y1)
        if best is None:
            return None

        cx, cy, r = best
        # 转回全图坐标
        cx_full = cx + x1
        cy_full = cy + y1

        # 计算正方形裁剪区域（留 5px 余量）
        margin = 5
        region = (
            max(0, cx_full - r - margin),
            max(0, cy_full - r - margin),
            2 * r + 2 * margin,
            2 * r + 2 * margin,
        )

        logger.info(f"检测到小地图: center=({cx_full},{cy_full}), r={r}, "
                    f"region={region}")
        return region

    def _pick_best_circle(self, circles, roi_shape, offset_x, offset_y):
        """从候选圆中选最佳小地图

        优先选择：
        1. 在 ROI 右上角区域的
        2. 半径接近 80-90px 的
        3. 离 ROI 右上角最近的
        """
        roi_h, roi_w = roi_shape[:2]
        target_r = self._target_r  # scaled expected radius
        best_score = float('inf')
        best = None

        for c in circles:
            cx, cy, r = int(c[0]), int(c[1]), int(c[2])

            # 转到全图坐标做评分
            cx_full = cx + offset_x
            cy_full = cy + offset_y

            # 评分：越小越好
            # 1. 半径偏差（权重高）
            r_diff = abs(r - target_r) * 3
            # 2. 离右上角的距离（偏好右上角）
            dist_to_top_right = (roi_w - cx) + cy
            # 3. 边界检查（不能太靠近边缘）
            if cx - r < 5 or cy - r < 5:
                continue

            score = r_diff + dist_to_top_right * 0.1
            if score < best_score:
                best_score = score
                best = (cx, cy, r)

        return best

    def _verify_cached(self, frame):
        """快速验证缓存位置是否仍然有效

        检查缓存区域是否包含圆形深色边框
        """
        if self._cached_region is None:
            return False

        x, y, w, h = self._cached_region
        fh, fw = frame.shape[:2]

        # 边界检查
        if x < 0 or y < 0 or x + w > fw or y + h > fh:
            return False

        crop = frame[y:y + h, x:x + w]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

        # 检查中心区域是否有内容（不是纯黑/纯白）
        center = gray[h // 4:3 * h // 4, w // 4:3 * w // 4]
        mean_val = np.mean(center)
        if mean_val < 10 or mean_val > 250:
            return False

        # 检查边缘是否有深色环（小地图边框）
        edges = gray[2:h - 2, 2:w - 2]
        edge_mean = np.mean(edges)
        center_mean = np.mean(center)

        # 边框应该比中心暗
        if edge_mean > center_mean * 1.5:
            return False

        return True

    def reset(self):
        """清除缓存，强制下次重新检测"""
        self._cached_region = None
        self._cache_fail_count = 0

    @property
    def cached_region(self):
        return self._cached_region
