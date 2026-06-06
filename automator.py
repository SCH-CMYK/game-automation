"""
自动化引擎 — 视觉寻路采矿（已验证逻辑移植版）
"""
import time
import random
import math
import logging

logger = logging.getLogger("gameauto.automator")


class Automator:
    def __init__(self, capture, vision, controller):
        self.capture = capture
        self.vision = vision
        self.controller = controller
        self.running = False
        self.paused = False
        self.stats = {"clicks": 0, "detections": 0, "loops": 0}

    def start(self): self.running = True; self.paused = False
    def stop(self): self.running = False
    def pause(self): self.paused = True
    def resume(self): self.paused = False
    def reset_stats(self): self.stats = {"clicks": 0, "detections": 0, "loops": 0}

    @staticmethod
    def match_locked(detections, locked_pos, max_dist=350):
        """匹配锁定目标：在检测列表中找最接近 locked_pos 的矿"""
        lx, ly = locked_pos
        best, best_dist = None, max_dist
        for d in detections:
            dist = math.hypot(d["center"][0] - lx, d["center"][1] - ly)
            if dist < best_dist:
                best_dist, best = dist, d
        return best

    @staticmethod
    def calc_turn(dx, dy, dead_zone=5, turn_scale=0.65, turn_decay=150, cap=120):
        """计算转向量（指数衰减，死区 + 上限）"""
        dist = math.hypot(dx, dy)
        if dist < dead_zone:
            return 0, 0
        scale = turn_scale * (1.0 - math.exp(-dist / turn_decay))
        cap = min(cap, int(dist * scale))
        if cap < 1:
            return 0, 0
        return (max(-cap, min(cap, int(dx * scale))),
                max(-cap, min(cap, int(dy * scale))))

    # === 采矿主循环 ===
    def walk_to_mine(self, walk_key: str = 'w'):
        logger.info("开始 (多模型联动)")
        w_down = False
        lost_count = 0
        max_lost = 20
        self._blind_count = 0
        AIM_DX = 50
        GROWTH_NEEDED = 1.10
        WALK_RANGE = 300
        DEAD_ZONE = 5
        DIST_FAR = 0.03
        DIST_CLOSE = 0.10
        self._scan_dir = random.choice([-1, 1])
        avoid_cooldown = 0
        force_stop = False      # 强制停步标志，只采矿/避障时置 True

        ore_track = None
        locked_target = None
        last_mine_time = 0.0
        last_seen_pos = None

        def stop_walk():
            nonlocal w_down
            if w_down:
                self.controller.key_up(walk_key)
                w_down = False
                time.sleep(0.01)

        def start_walk():
            nonlocal w_down
            if not w_down:
                self.controller.key_down(walk_key)
                w_down = True

        def do_mine(blind=False):
            nonlocal last_mine_time, locked_target
            stop_walk()
            time.sleep(0.2)
            if not blind:
                best_det = None
                for i in range(10):
                    f = self.capture.grab()
                    all_dets = self.vision.detect_all(f)["ore"]
                    det = Automator.match_locked(all_dets, locked_target) if locked_target and all_dets else (
                        self.vision.find_best_ore(f))
                    if det is None:
                        break
                    best_det = det
                    fx = det["center"][0] - f.shape[1] // 2
                    fy = det["center"][1] - f.shape[0] // 2
                    # 1px 内认为已对准中心
                    if abs(fx) <= 1 and abs(fy) <= 1:
                        break
                    # 修正公式：最小移动 55%，确保小误差也能收敛
                    mag = math.hypot(fx, fy)
                    factor = max(0.55, 1.0 - math.exp(-mag / 80))
                    move_x = int(round(fx * factor))
                    move_y = int(round(fy * factor))
                    if move_x == 0 and move_y == 0 and abs(fx) <= 2 and abs(fy) <= 2:
                        break  # 太近无法移动，直接采
                    self.controller.move_relative(move_x, move_y)
                    time.sleep(0.06)

                # 最终确认
                f = self.capture.grab()
                all_dets = self.vision.detect_all(f)["ore"]
                det = Automator.match_locked(all_dets, locked_target) if locked_target and all_dets else (
                    self.vision.find_best_ore(f))
                if det:
                    fx = det["center"][0] - f.shape[1] // 2
                    fy = det["center"][1] - f.shape[0] // 2
                    if abs(fx) > 3 or abs(fy) > 3:
                        self.controller.move_relative(int(round(fx * 0.7)), int(round(fy * 0.7)))
                        time.sleep(0.05)

            logger.info("长按采集 2s (中心对准)")
            self.controller.mouse_down("left")
            time.sleep(2.0)
            self.controller.mouse_up("left")
            self.stats["clicks"] += 1
            self.stats["loops"] += 1
            last_mine_time = time.time()
            time.sleep(6.0)

        def calc_turn(dx, dy):
            return Automator.calc_turn(dx, dy, DEAD_ZONE, turn_scale=0.65, turn_decay=150, cap=120)

        try:
            while self.running:
                if self.paused:
                    stop_walk()
                    time.sleep(0.1)
                    continue

                frame = self.capture.grab()
                screen_h, screen_w = frame.shape[:2]
                screen_cx, screen_cy = screen_w // 2, screen_h // 2

                # 一次推理得到所有类别
                all = self.vision.detect_all(frame)
                self.stats["detections"] += 1
                creatures = all["creature"]
                ores = all["ore"]
                obstacles = all["obstacle"]
                characters = all["character"]
                char_pos = characters[0]["center"] if characters else None

                # === 野生精灵检测 ===
                if creatures and avoid_cooldown <= 0:
                    near_creatures = [c for c in creatures
                                      if abs(c["center"][0] - screen_cx) < screen_w * 0.3]
                    if near_creatures:
                        logger.info(f"检测到 {len(near_creatures)} 只野生精灵, 绕开")
                        force_stop = True
                        dodge = random.choice([-400, 400])
                        self.controller.move_relative(dodge, 0)
                        avoid_cooldown = 15
                        time.sleep(0.15)
                        continue

                # === 障碍物检测 ===
                if obstacles and avoid_cooldown <= 0:
                    # 障碍物在画面中心 = 挡路
                    blocked = any(abs(o["center"][0] - screen_cx) < screen_w * 0.2
                                  for o in obstacles)
                    if blocked:
                        logger.info("前方障碍, 转向绕行")
                        force_stop = True
                        dodge = random.choice([-500, 500])
                        self.controller.move_relative(dodge, 0)
                        avoid_cooldown = 10
                        time.sleep(0.15)
                        continue

                if avoid_cooldown > 0:
                    avoid_cooldown -= 1

                all_dets = ores

                # 锁定目标匹配
                det = None
                if locked_target and all_dets:
                    det = Automator.match_locked(all_dets, locked_target)
                    if det:
                        locked_target = det["center"]
                        last_seen_pos = det["center"]
                elif all_dets:
                    det = min(all_dets, key=lambda d: math.hypot(
                        d["center"][0] - screen_cx, d["center"][1] - screen_cy))
                    if locked_target is None:
                        locked_target = det["center"]
                        last_seen_pos = det["center"]

                # 没找到矿
                if det is None:
                    lost_count += 1
                    # 盲挖：矿刚丢 + 上次位置在中心 + 不在冷却
                    if (ore_track and last_seen_pos and lost_count < 5
                            and abs(last_seen_pos[0] - screen_cx) < 40
                            and time.time() - last_mine_time > 6.0):
                        logger.info("盲点采矿")
                        do_mine(blind=True)
                        ore_track = locked_target = last_seen_pos = None
                        lost_count = 0
                        continue
                    if ore_track and last_seen_pos and lost_count <= max_lost:
                        growth = ore_track["smoothed_area"] / max(ore_track["initial_area"], 1)
                        px, py = last_seen_pos
                        was_large = ore_track["smoothed_area"] > 2000
                        area_shrinking = (lost_count > 4 and ore_track["smoothed_area"] < ore_track["initial_area"] * 0.8)
                        if (growth >= GROWTH_NEEDED or area_shrinking or was_large) and abs(px - screen_cx) < AIM_DX * 2:
                            logger.info(f"盲点采矿 growth={growth:.1f}x")
                            do_mine(blind=True)
                            ore_track = locked_target = last_seen_pos = None
                            lost_count = 0
                            continue
                        time.sleep(0.06)
                        continue
                    if lost_count > max_lost:
                        ore_track = locked_target = last_seen_pos = None
                        tick = (lost_count - max_lost) // 8
                        scan_phase = tick % 4
                        start_walk()
                        if (lost_count - max_lost) % 8 == 0:
                            if scan_phase == 0:
                                self._scan_dir = random.choice([-1, 1])
                            direction = self._scan_dir if scan_phase < 2 else -self._scan_dir
                            self.controller.move_relative(direction * (350 if scan_phase < 2 else 250), 0)
                        if lost_count > max_lost + 60:
                            lost_count = 0
                    time.sleep(0.1)
                    continue

                # 检测到矿
                if time.time() - last_mine_time < 3.0:
                    stop_walk()
                    time.sleep(0.1)
                    continue

                if ore_track is None:
                    ore_track = {"initial_area": float(det["area"]), "smoothed_area": float(det["area"]), "pos": det["center"]}
                    last_seen_pos = det["center"]

                lost_count = 0
                cx, cy = det["center"]
                dx, dy = cx - screen_cx, cy - screen_cy
                bbox_area = float(det["area"])

                ore_track["smoothed_area"] = ore_track["smoothed_area"] * 0.7 + bbox_area * 0.3
                ore_track["pos"] = (cx, cy)
                growth = ore_track["smoothed_area"] / max(ore_track["initial_area"], 1)

                # 距离分档
                bbox_h = det["bbox"][3] - det["bbox"][1]
                bbox_w = det["bbox"][2] - det["bbox"][0]
                bbox_h_ratio = bbox_h / screen_h

                is_far = bbox_h_ratio < DIST_FAR         # 远
                is_close = bbox_h_ratio > DIST_CLOSE      # 近
                is_mid = not is_far and not is_close       # 中
                growth_ok = growth >= GROWTH_NEEDED
                too_close = growth < 0.90 and bbox_area > 2000

                # 远距离：超快转向
                if is_far and abs(dx) > WALK_RANGE:
                    fast_x = max(-130, min(130, int(dx * 0.60)))
                    fast_y = max(-130, min(130, int(dy * 0.60)))
                    self.controller.move_relative(fast_x, fast_y)
                    time.sleep(0.005)
                else:
                    turn_x, turn_y = calc_turn(dx, dy)
                    if turn_x or turn_y:
                        self.controller.move_relative(turn_x, turn_y)
                        time.sleep(0.01)

                # 采矿判断：矿石 bbox + 角色 bbox 距离
                char_to_ore_dist = None
                if char_pos:
                    char_to_ore_dist = math.hypot(cx - char_pos[0], cy - char_pos[1])
                # 触发条件：矿够大 OR 增长达标 OR 角色离矿很近
                can_mine = (is_close or growth_ok or too_close or
                            (char_to_ore_dist is not None and char_to_ore_dist < 150))
                if can_mine and abs(dx) < AIM_DX:
                    info = f"dx={dx} bbox_h={bbox_h} growth={growth:.1f}x"
                    if char_to_ore_dist: info += f" char2ore={char_to_ore_dist:.0f}px"
                    logger.info(f"触发采矿 {info}")
                    force_stop = True
                    do_mine()
                    ore_track = locked_target = last_seen_pos = None
                    force_stop = False  # 采矿后立即重置，避免卡在 lost-walk 阶段
                    continue

                # 走路控制：矿在前方就 W 按到底，不松
                if force_stop:
                    stop_walk()
                    force_stop = False
                elif is_close or growth_ok or too_close:
                    # 够近了 → 停步，只转鼠标精瞄
                    stop_walk()
                elif abs(dx) < WALK_RANGE:
                    # 矿在前方 → 一直走不松
                    start_walk()
                else:
                    stop_walk()
                time.sleep(0.03)
        finally:
            stop_walk()
