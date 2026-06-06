"""
路线规划器 — 颜色+箭头匹配导航引擎

Pipeline（每帧 ~25ms）:
  截图 → 裁剪小地图 → 甜甜圈遮罩
    ├─ 箭头朝向检测（白色 HSV，~2ms）
    ├─ SIFT 位置匹配（局部窗口，~15ms）
    │   └─ 失败 → 颜色直方图回退（~5ms）
    └─ 导航转向计算
"""
import cv2
import numpy as np
import math
import time
import threading
import logging

from src.utils.config import ROUTE, AI
from src.engine.minimap_detector import MinimapDetector

logger = logging.getLogger("gameauto.route")


def distance_2d(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


class RoutePlanner:
    """颜色+箭头匹配导航引擎"""

    def __init__(self, controller, capture):
        self.controller = controller
        self.capture = capture
        self.waypoints = []
        self.current_wp_idx = 1
        self.running = False
        self.minimap_region = None  # (x, y, w, h) 屏幕坐标
        self._minimap_detector = MinimapDetector()  # 自动检测器
        self._hybrid_positioner = None  # 混合定位引擎

logger = logging.getLogger("gameauto.route")


class RoutePlanner:
    """颜色+箭头匹配导航引擎"""

    def __init__(self, controller, capture):
        self.controller = controller
        self.capture = capture
        self.waypoints = []
        self.current_wp_idx = 1
        self.running = False
        self.minimap_region = None  # (x, y, w, h) 屏幕坐标
        self._minimap_detector = MinimapDetector()  # 自动检测器
        self._ai_positioner = None  # AI 定位引擎（可选）
        self._hybrid_positioner = None  # 混合定位引擎

        # SIFT
        self._sift = cv2.SIFT_create(nfeatures=ROUTE.sift_nfeatures)
        self._clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
        self._kp_big = self._des_big = None  # 大地图全局特征
        self._kp_local = self._des_local = None  # 局部窗口特征
        self._local_origin = None  # 局部窗口在大地图上的原点

        # FLANN 匹配器
        FLANN_INDEX_KDTREE = 1
        self._flann = cv2.FlannBasedMatcher(
            dict(algorithm=FLANN_INDEX_KDTREE, trees=5),
            dict(checks=100)
        )

        # 甜甜圈遮罩（预计算）
        sz = ROUTE.minimap_size
        self._donut_mask = np.zeros((sz, sz), dtype=np.uint8)
        cv2.circle(self._donut_mask, (sz // 2, sz // 2),
                   ROUTE.mask_outer_radius, 255, -1)
        cv2.circle(self._donut_mask, (sz // 2, sz // 2),
                   ROUTE.mask_inner_radius, 0, -1)

        # 箭头 HSV 阈值
        self._arrow_hsv_low = np.array(ROUTE.arrow_hsv_low, dtype=np.uint8)
        self._arrow_hsv_high = np.array(ROUTE.arrow_hsv_high, dtype=np.uint8)

        # 位置跟踪
        self._last_pos = None  # (x, y) 大地图坐标
        self._sift_fail_count = 0
        self._walk_held = False  # W 键是否按住（实例状态）
        self._heading_ema = None  # 箭头朝向 EMA 平滑

        # 大地图缓存（用于颜色回退）
        self._big_map_hsv = None

        logger.info("路线引擎初始化: 颜色+箭头匹配")

    # ========== 配置接口 ==========

    def set_logic_map(self, image):
        """加载大地图，尝试加载 AI 定位模型（不预计算全局 SIFT，太耗内存）"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
        self._logic_gray = gray
        self._big_map_hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV) if len(image.shape) == 3 else None

        # 不预计算全局 SIFT（6144×5888 需要 578MB，会 OOM）
        # 改为按需在局部窗口内计算
        self._kp_big = None
        self._des_big = None
        logger.info(f"大地图已加载: {image.shape[1]}x{image.shape[0]}")

        # 加载混合定位引擎（AI + LoFTR + SIFT）
        self._load_hybrid_positioner(image)

    def _load_hybrid_positioner(self, map_image):
        """加载混合定位引擎（Kornia LoFTR，不依赖 AI 模型）"""
        try:
            from src.engine.hybrid_positioner import HybridPositioner
            self._hybrid_positioner = HybridPositioner("", map_image)
            self._hybrid_positioner.set_map(map_image)
            logger.info("混合定位引擎已加载（Kornia LoFTR）")
        except Exception as e:
            logger.warning(f"混合定位加载失败: {e}")

    def set_minimap_region(self, x, y, w, h):
        """设置小地图在屏幕上的位置"""
        self.minimap_region = (x, y, w, h)

    # ========== 小地图处理 ==========

    def grab_minimap(self, screenshot):
        """从截图裁剪小地图区域（自动检测或手动坐标）"""
        # 如果没有手动设置区域，用自动检测
        if not self.minimap_region:
            region = self._minimap_detector.detect(screenshot)
            if region is not None:
                self.minimap_region = region
                logger.debug(f"自动检测小地图: {region}")
            else:
                return None

        x, y, w, h = self.minimap_region
        if y + h > screenshot.shape[0] or x + w > screenshot.shape[1]:
            # 坐标越界，重置并重新检测
            self.minimap_region = None
            self._minimap_detector.reset()
            return None
        return screenshot[y:y + h, x:x + w]

    def apply_donut_mask(self, minimap):
        """应用甜甜圈遮罩：消除角落、中心箭头、迷雾"""
        h, w = minimap.shape[:2]
        if (h, w) != self._donut_mask.shape[:2]:
            # 小地图尺寸和预设不同，动态调整遮罩
            mask = np.zeros((h, w), dtype=np.uint8)
            cx, cy = w // 2, h // 2
            outer_r = min(cx, cy)
            inner_r = max(1, int(ROUTE.mask_inner_radius * h / ROUTE.minimap_size))
            cv2.circle(mask, (cx, cy), outer_r, 255, -1)
            cv2.circle(mask, (cx, cy), inner_r, 0, -1)
        else:
            mask = self._donut_mask
        return cv2.bitwise_and(minimap, minimap, mask=mask)

    # ========== 箭头朝向检测 ==========

    def get_arrow_heading(self, minimap):
        """检测玩家箭头朝向（白色箭头，直接读取方向）

        Returns:
            float: 朝向角度（度，0=北/上，顺时针正方向），或 None
        """
        sz = minimap.shape[0]
        cs = ROUTE.arrow_crop_size
        half = cs // 2
        cx, cy = sz // 2, sz // 2

        # 裁剪中心区域
        x1, y1 = max(0, cx - half), max(0, cy - half)
        x2, y2 = min(sz, cx + half), min(sz, cy + half)
        crop = minimap[y1:y2, x1:x2]

        # HSV 白色阈值
        hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, self._arrow_hsv_low, self._arrow_hsv_high)

        # 形态学去噪
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # 找最大轮廓
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        # 过滤面积太小的噪声
        valid = [c for c in contours if cv2.contourArea(c) >= ROUTE.arrow_min_area]
        if not valid:
            return None

        largest = max(valid, key=cv2.contourArea)
        if len(largest) < 5:
            # 点数不足，用 minAreaRect
            rect = cv2.minAreaRect(largest)
            angle = rect[2]
        else:
            # 用拟合椭圆
            ellipse = cv2.fitEllipse(largest)
            angle = ellipse[2]  # OpenCV 椭圆角度：0-180

        # 将 OpenCV 角度转换为标准方向角度
        # OpenCV: 0°=水平, 90°=垂直
        # 我们: 0°=北(上), 90°=东(右), 顺时针
        heading = (90.0 - angle) % 360.0
        return heading

    # ========== SIFT 位置匹配 ==========

    def get_position_sift(self, minimap):
        """用 SIFT 匹配获取玩家在大地图上的位置

        策略：只在上次位置附近做局部搜索（避免全图 OOM）

        Returns:
            (x, y) 大地图坐标，或 None
        """
        if self._last_pos is None:
            return None  # 没有参考位置，SIFT 无法工作（交给 AI）

        mm_masked = self.apply_donut_mask(minimap)
        gray = cv2.cvtColor(mm_masked, cv2.COLOR_BGR2GRAY) if len(mm_masked.shape) == 3 else mm_masked
        gray = self._clahe.apply(gray)

        # 生成与灰度图同尺寸的遮罩
        h, w = gray.shape[:2]
        if (h, w) != self._donut_mask.shape[:2]:
            sift_mask = np.zeros((h, w), dtype=np.uint8)
            cx, cy = w // 2, h // 2
            outer_r = min(cx, cy)
            inner_r = max(1, int(ROUTE.mask_inner_radius * h / ROUTE.minimap_size))
            cv2.circle(sift_mask, (cx, cy), outer_r, 255, -1)
            cv2.circle(sift_mask, (cx, cy), inner_r, 0, -1)
        else:
            sift_mask = self._donut_mask

        kp_mm, des_mm = self._sift.detectAndCompute(gray, sift_mask)
        if des_mm is None or len(kp_mm) < ROUTE.sift_min_matches:
            return None

        mm_shape = gray.shape[:2]

        # 只做局部搜索（避免全图 SIFT OOM）
        pos = self._search_local(des_mm, kp_mm, mm_shape)
        return pos

    def _search_global(self, des_mm, kp_mm, mm_shape):
        """全局 SIFT 匹配"""
        if self._des_big is None or len(self._des_big) < ROUTE.sift_min_matches:
            return None
        return self._match_sift(des_mm, kp_mm, self._des_big, self._kp_big, 0, 0, mm_shape=mm_shape)

    def _search_local(self, des_mm, kp_mm, mm_shape):
        """局部 SIFT 匹配（在上次位置附近 400x400 窗口）"""
        if self._des_big is None:
            return None

        lx, ly = self._last_pos
        big_h, big_w = self._logic_gray.shape[:2]
        half = ROUTE.search_window_size // 2

        # 裁剪局部窗口
        x1 = max(0, int(lx - half))
        y1 = max(0, int(ly - half))
        x2 = min(big_w, int(lx + half))
        y2 = min(big_h, int(ly + half))

        local_gray = self._logic_gray[y1:y2, x1:x2]
        local_enhanced = self._clahe.apply(local_gray)

        kp_local, des_local = self._sift.detectAndCompute(local_enhanced, None)
        if des_local is None or len(kp_local) < ROUTE.sift_min_matches:
            return None

        result = self._match_sift(des_mm, kp_mm, des_local, kp_local, x1, y1, mm_shape=mm_shape)
        if result is not None:
            # 验证结果在窗口内（避免跳跃到远处）
            rx, ry = result
            dist = math.hypot(rx - lx, ry - ly)
            if dist > ROUTE.search_window_size * 0.6:
                logger.debug(f"局部匹配结果 ({rx:.0f},{ry:.0f}) 离上次位置太远 ({dist:.0f}px)")
                return None
        return result

    def _match_sift(self, des_mm, kp_mm, des_target, kp_target, offset_x, offset_y, mm_shape=None):
        """通用 SIFT 匹配逻辑

        Args:
            des_mm: 小地图描述子
            kp_mm: 小地图关键点
            des_target: 目标描述子（全局或局部）
            kp_target: 目标关键点
            offset_x, offset_y: 局部窗口偏移
            mm_shape: 小地图实际尺寸 (h, w)，用于计算中心点

        Returns:
            (x, y) 大地图坐标，或 None
        """
        if des_target is None or len(des_target) < ROUTE.sift_min_matches:
            return None

        try:
            matches = self._flann.knnMatch(des_mm, des_target, k=2)
        except cv2.error:
            return None

        # Lowe ratio test
        good = [m for m, n in matches
                if m.distance < ROUTE.sift_ratio * n.distance]
        if len(good) < ROUTE.sift_min_matches:
            return None

        # 单应性矩阵
        src = np.float32([kp_mm[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
        dst = np.float32([kp_target[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

        M, mask = cv2.findHomography(src, dst, cv2.RANSAC,
                                     ROUTE.sift_ransac_threshold)
        if M is None:
            return None

        # 变换小地图中心到大地图坐标
        if mm_shape is not None:
            mh, mw = mm_shape
        else:
            mh, mw = self._donut_mask.shape[:2]
        center = np.array([[mw / 2, mh / 2]], dtype=np.float32).reshape(-1, 1, 2)
        pos = cv2.perspectiveTransform(center, M).reshape(2)

        # 加上局部窗口偏移
        x = float(pos[0]) + offset_x
        y = float(pos[1]) + offset_y

        # 内点比例检查（至少 60% 的匹配是内点）
        inlier_ratio = np.sum(mask) / len(mask) if mask is not None else 0
        if inlier_ratio < 0.6:
            logger.debug(f"SIFT 内点比例过低: {inlier_ratio:.2f}")
            return None

        return (x, y)

    # ========== 颜色直方图回退 ==========

    def get_position_color(self, minimap):
        """颜色直方图匹配（SIFT 连续失败时的回退方案）

        在大地图上滑动窗口，找与小地图颜色分布最相似的位置

        Returns:
            (x, y) 大地图坐标，或 None
        """
        if self._big_map_hsv is None:
            return None

        mm_masked = self.apply_donut_mask(minimap)
        mm_hsv = cv2.cvtColor(mm_masked, cv2.COLOR_BGR2HSV)

        # 计算小地图遮罩区域的 HSV 直方图
        h, w = mm_hsv.shape[:2]
        if (h, w) != self._donut_mask.shape[:2]:
            color_mask = np.zeros((h, w), dtype=np.uint8)
            cx, cy = w // 2, h // 2
            outer_r = min(cx, cy)
            inner_r = max(1, int(ROUTE.mask_inner_radius * h / ROUTE.minimap_size))
            cv2.circle(color_mask, (cx, cy), outer_r, 255, -1)
            cv2.circle(color_mask, (cx, cy), inner_r, 0, -1)
        else:
            color_mask = self._donut_mask
        mm_hist = cv2.calcHist([mm_hsv], [0, 1], color_mask,
                               [ROUTE.color_histogram_bins, ROUTE.color_histogram_bins],
                               [0, 180, 0, 256])
        cv2.normalize(mm_hist, mm_hist, 0, 1, cv2.NORM_MINMAX)

        # 在大地图上滑动窗口
        big_h, big_w = self._big_map_hsv.shape[:2]
        step = ROUTE.color_search_step
        mm_sz = ROUTE.minimap_size
        half = mm_sz // 2

        # 如果有上次位置，优先搜索附近区域
        if self._last_pos is not None:
            lx, ly = int(self._last_pos[0]), int(self._last_pos[1])
            search_radius = ROUTE.search_window_size
            x_start = max(0, lx - search_radius)
            y_start = max(0, ly - search_radius)
            x_end = min(big_w - mm_sz, lx + search_radius)
            y_end = min(big_h - mm_sz, ly + search_radius)
        else:
            x_start, y_start = 0, 0
            x_end = big_w - mm_sz
            y_end = big_h - mm_sz

        best_score = -1
        best_pos = None

        for y in range(y_start, y_end, step):
            for x in range(x_start, x_end, step):
                # 在大地图上裁剪对应区域
                patch = self._big_map_hsv[y:y + mm_sz, x:x + mm_sz]
                if patch.shape[:2] != (mm_sz, mm_sz):
                    continue

                patch_hist = cv2.calcHist([patch], [0, 1], None,
                                          [ROUTE.color_histogram_bins,
                                           ROUTE.color_histogram_bins],
                                          [0, 180, 0, 256])
                cv2.normalize(patch_hist, patch_hist, 0, 1, cv2.NORM_MINMAX)

                # 比较直方图（相关性，越大越好）
                score = cv2.compareHist(mm_hist, patch_hist,
                                        cv2.HISTCMP_CORREL)
                if score > best_score:
                    best_score = score
                    best_pos = (x + half, y + half)

        if best_pos and best_score > 0.3:
            logger.info(f"颜色回退定位: ({best_pos[0]:.0f},{best_pos[1]:.0f}) "
                        f"score={best_score:.3f}")
            return best_pos

        return None

    # ========== 综合定位 ==========

    def get_position(self, minimap):
        """定位：LoFTR + 跳变过滤"""
        if minimap is None:
            return self._last_pos

        if hasattr(self, '_hybrid_positioner') and self._hybrid_positioner is not None:
            pos = self._hybrid_positioner.get_position(minimap)
            if pos is not None:
                # 跳变过滤：突然跳 >100px → 忽略
                if self._last_pos is not None:
                    jump = distance_2d(pos, self._last_pos)
                    if jump > 100:
                        return self._last_pos  # 保持上次位置
                self._last_pos = pos
                return pos

        return self._last_pos

    # ========== 导航 ==========

    def run_route(self, automator):
        """执行路线导航（最简版：死循航 + 箭头朝向）"""
        self.running = True
        self._walk_held = False

        if len(self.waypoints) < 2:
            logger.warning("途经点不足")
            self.running = False
            return

        # 初始化位置：从第一个途经点开始
        if self._hybrid_positioner is not None:
            self._hybrid_positioner.init_position(
                self.waypoints[0][0], self.waypoints[0][1])

        logger.info(f"开始导航: {len(self.waypoints)} 个途经点")

        try:
            while self.running and self.current_wp_idx < len(self.waypoints):
                self._go_to_next(automator)
        except Exception as e:
            logger.error(f"导航异常: {e}", exc_info=True)
        finally:
            self._stop_walk()
            logger.info("导航结束")
            self.running = False

    def _recover_position(self, fallback_x, fallback_y):
        """脱离战斗/采矿后立即定位，获取当前真实坐标"""
        self._walk_held = False
        # 等 UI 消失 + 小地图恢复
        for attempt in range(6):
            time.sleep(0.15)
            frame = self.capture.grab()
            mm = self.grab_minimap(frame)
            if mm is not None and hasattr(self, '_hybrid_positioner') and self._hybrid_positioner:
                # 先用大致坐标初始化，给 LoFTR 一个搜索起点
                self._hybrid_positioner.init_position(fallback_x, fallback_y)
                pos = self._hybrid_positioner.get_position(mm)
                if pos is not None:
                    logger.info(f"  恢复定位成功: ({int(pos[0])}, {int(pos[1])})")
                    return pos
                # LoFTR 没匹配到：可能还在 UI 过渡，再等等
            if attempt == 2:
                # 第 3 次还没定位到，往前走一小步触发画面刷新
                self.controller.key_down('w')
                time.sleep(0.3)
                self.controller.key_up('w')
        logger.info(f"  恢复定位超时，使用回退坐标: ({fallback_x}, {fallback_y})")
        return (float(fallback_x), float(fallback_y))

    def _stop_walk(self):
        if self._walk_held:
            try: self.controller.key_up('w')
            except: pass
            try: self.controller.key_up('shift')
            except: pass
            self._walk_held = False

    def _go_to_next(self, automator):
        """走到下一个途经点"""
        tx, ty, name = self.waypoints[self.current_wp_idx]
        logger.info(f"==> [{self.current_wp_idx}/{len(self.waypoints)-1}] {name} ({tx},{ty})")

        self.controller.key_down('w')
        self.controller.key_down('shift')
        self._walk_held = True

        prev_pos = None
        for step in range(200):
            if not self.running:
                break

            # 定期清理内存
            if step % 50 == 0:
                import gc; gc.collect()

            # 1. 定位
            frame = self.capture.grab()
            mm = self.grab_minimap(frame)
            pos = self.get_position(mm)
            if pos is None:
                time.sleep(0.05)
                continue

            # 2. 战斗检测（每帧，最高优先级）
            self._minimap_detector.reset()
            r = self._minimap_detector.detect(frame)
            in_battle = (r is None or r[0] < 1700 or r[1] > 200)
            battle_ok = time.time() - getattr(self, '_last_battle_time', 0) > 8.0
            if in_battle and battle_ok:
                logger.info("  进入战斗，退出中...")
                time.sleep(2.0)
                self._stop_walk()
                self._escape_battle(frame)
                self._last_battle_time = time.time()
                if self.current_wp_idx + 1 < len(self.waypoints):
                    self.current_wp_idx += 1
                    tx, ty = self.waypoints[self.current_wp_idx][0], self.waypoints[self.current_wp_idx][1]
                    name = self.waypoints[self.current_wp_idx][2]
                    logger.info(f"  战斗后跳至 [{self.current_wp_idx}] {name}")
                # 恢复定位：立即扫小地图获取真实位置
                self._last_pos = self._recover_position(tx, ty)
                import gc; gc.collect()
                self.controller.key_down('w')
                self.controller.key_down('shift')
                self._walk_held = True
                prev_pos = None
                continue

            # 3. 计算距离
            px_now, py_now = pos
            dx = tx - px_now
            dy = ty - py_now
            dist = math.hypot(dx, dy)

            # 4. 路线纠正
            if dist > 150:
                best, bi = dist, self.current_wp_idx
                for i in range(self.current_wp_idx, min(self.current_wp_idx + 5, len(self.waypoints))):
                    d = math.hypot(px_now - self.waypoints[i][0], py_now - self.waypoints[i][1])
                    if d < best:
                        best, bi = d, i
                if bi != self.current_wp_idx and best < dist * 0.8:
                    logger.info(f"  纠正路线 → [{bi}]")
                    self.current_wp_idx = bi
                    tx, ty = self.waypoints[bi][0], self.waypoints[bi][1]
                    name = self.waypoints[bi][2]
                    dx, dy = tx - px_now, ty - py_now
                    dist = math.hypot(dx, dy)

            # 5. 实时矿检测：有矿就停，采完再走
            if automator.vision.loaded and step % 2 == 0:
                ores = automator.vision.detect_all(frame, conf=0.5).get("ore", [])
                if ores:
                    logger.info("  矿！")
                    self._stop_walk()
                    self._quick_mine(automator, frame)
                    # 采矿后恢复：立即扫小地图获取真实位置
                    self._last_pos = self._recover_position(tx, ty)
                    self.controller.key_down('w')
                    self.controller.key_down('shift')
                    self._walk_held = True
                    prev_pos = None
                    continue

            # 6. 到达
            if dist < 40:
                logger.info(f"  到达 {name}! dist={dist:.0f}")
                break

            # 6. 转向
            if prev_pos and (px_now != prev_pos[0] or py_now != prev_pos[1]):
                actual_angle = math.degrees(math.atan2(px_now - prev_pos[0], -(py_now - prev_pos[1])))
                desired_angle = math.degrees(math.atan2(dx, -dy))
                correction = desired_angle - actual_angle
                while correction > 180: correction -= 360
                while correction < -180: correction += 360
                if abs(correction) > 2:
                    turn = int(correction * 20.0)
                    self.controller.move_relative(max(-300, min(300, turn)), 0)

            if step % 5 == 0:
                logger.info(f"  [{step}] ({int(px_now)},{int(py_now)}) dist={dist:.0f}")

            prev_pos = (px_now, py_now)
            time.sleep(0.08)

        self._stop_walk()
        if not self.running:
            return
        self.current_wp_idx += 1

    def _quick_mine(self, automator, frame):
        """停住采矿：一直采到屏幕没有矿为止"""
        count = 0
        max_mines = 5
        while count < max_mines:
            f = self.capture.grab()
            ores = automator.vision.detect_all(f, conf=0.4).get("ore", [])
            if not ores:
                logger.info(f"  采完（{count}次）")
                return
            h, w = f.shape[:2]
            best = min(ores, key=lambda d: math.hypot(d["center"][0] - w//2, d["center"][1] - h//2))
            # 瞄准（1px内停）
            for _ in range(5):
                f2 = self.capture.grab()
                ore = automator.vision.find_best_ore(f2)
                if ore is None:
                    break
                fx = ore["center"][0] - w // 2
                fy = ore["center"][1] - h // 2
                if abs(fx) < 1 and abs(fy) < 1:
                    break
                self.controller.move_relative(int(fx * 0.8), int(fy * 0.8))
                time.sleep(0.03)
            # 丢球
            self.controller.mouse_down("left")
            time.sleep(0.5)
            self.controller.mouse_up("left")
            time.sleep(5.0)
            count += 1
            logger.info(f"  采矿 {count}/{max_mines}")
            # 两次还没采到 → 往前走一步（避死角）
            if count == 2 and automator.vision.detect_all(self.capture.grab(), conf=0.4).get("ore"):
                logger.info("  死角，向前走一步")
                self.controller.key_down('w')
                time.sleep(0.5)
                self.controller.key_up('w')
                time.sleep(0.5)
        logger.info("  采矿停止")

    def _escape_battle(self, _frame):
        """战斗逃跑：ESC+点击"""
        logger.info("  === 战斗逃跑 ===")
        self.controller.press('escape')
        time.sleep(1.5)
        self.controller.click(1114, 883)
        logger.info("  逃跑完成")

    def _mine_at_waypoint(self, automator, name):
        """在途经点执行采矿（检测到矿才采，否则直接跳过）"""
        if not automator.vision.loaded:
            logger.info(f"  [{name}] 模型未加载，跳过采矿")
            return

        # 快速检测是否有矿
        frame = self.capture.grab()
        dets = automator.vision.detect_all(frame)
        ores = dets.get("ore", [])
        if not ores:
            logger.info(f"  [{name}] 无矿，跳过")
            return

        logger.info(f"  [{name}] 开始采矿 ({len(ores)} 个矿)")
        automator.running = True
        mine_done = threading.Event()

        def _mine_worker():
            try:
                automator.walk_to_mine()
            finally:
                automator.running = False
                mine_done.set()

        t = threading.Thread(target=_mine_worker, daemon=True)
        t.start()

        # 等待采矿完成或超时
        if not mine_done.wait(timeout=ROUTE.mine_timeout):
            logger.warning(f"  [{name}] 采矿超时 ({ROUTE.mine_timeout}s)")
            automator.stop()
            mine_done.wait(timeout=2)  # 等待线程退出
        else:
            logger.info(f"  [{name}] 采矿完成")

    # ========== 停止 ==========

    def stop(self):
        """停止导航"""
        self.running = False
        try:
            self.controller.key_up('w')
        except Exception:
            pass
