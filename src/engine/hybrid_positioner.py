"""
定位引擎 — 原封不动复制参考项目 tracker_engine.py + main_hybrid.py

使用 Kornia LoFTR（和参考项目一模一样），不是 ONNX
"""
import cv2
import numpy as np
import torch
import kornia as K
from kornia.feature import LoFTR
import logging

logger = logging.getLogger("gameauto.hybrid_pos")


class HybridPositioner:
    """Kornia LoFTR 定位 — 和参考项目一模一样"""

    def __init__(self, model_path, map_image):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.map_h, self.map_w = map_image.shape[:2]

        # 大地图（彩色，和参考项目一样用 BGR）
        self.map_bgr = map_image.copy()
        self.map_gray = cv2.cvtColor(map_image, cv2.COLOR_BGR2GRAY)

        # 参考项目的 LoFTR 引擎（一模一样）
        self.loftr = LoFTR(pretrained='outdoor').to(self.device)
        self.loftr.eval()

        self._last_pos = None

        logger.info(f"Kornia LoFTR 定位引擎 (outdoor, {self.device}, 和参考项目一致)")

    def _loftr_preprocess(self, img_bgr):
        """预处理 — 和 tracker_engine.py 一模一样"""
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        h, w = img_gray.shape
        new_h, new_w = h - (h % 8), w - (w % 8)
        img_gray = cv2.resize(img_gray, (new_w, new_h))
        tensor = K.image_to_tensor(img_gray, False).float() / 255.0
        return tensor.to(self.device)

    def make_donut_mask(self, h, w):
        """甜甜圈遮罩 — 和参考项目一样"""
        mask = np.zeros((h, w), dtype=np.uint8)
        cx, cy = w // 2, h // 2
        outer_r = min(cx, cy)
        inner_r = 15
        cv2.circle(mask, (cx, cy), outer_r, 255, -1)
        cv2.circle(mask, (cx, cy), inner_r, 0, -1)
        return mask

    def set_map(self, map_image):
        self.map_bgr = map_image.copy()
        self.map_gray = cv2.cvtColor(map_image, cv2.COLOR_BGR2GRAY)
        self._last_pos = None

    def init_position(self, x, y):
        self._last_pos = (float(x), float(y))
        logger.info(f"初始位置: ({x:.0f}, {y:.0f})")

    def get_position(self, minimap_bgr):
        """定位 — 和 main_hybrid.py 一模一样"""
        if minimap_bgr is None or minimap_bgr.size == 0:
            return self._last_pos

        if self._last_pos is None:
            return None

        # 1. 甜甜圈遮罩（和参考项目一样）
        h, w = minimap_bgr.shape[:2]
        donut = self.make_donut_mask(h, w)
        minimap_masked = cv2.bitwise_and(minimap_bgr, minimap_bgr, mask=donut)

        # 2. 局部搜索区域（扩大窗口应对战斗后远跳）
        lx, ly = int(self._last_pos[0]), int(self._last_pos[1])
        r = 400
        x1, y1 = max(0, lx - r), max(0, ly - r)
        x2, y2 = min(self.map_w, lx + r), min(self.map_h, ly + r)
        local = self.map_bgr[y1:y2, x1:x2]

        if local.size == 0:
            return self._last_pos

        # 3. LoFTR 预处理（和 tracker_engine.py 一模一样）
        mini_tensor = self._loftr_preprocess(minimap_masked)
        local_tensor = self._loftr_preprocess(local)

        # 4. LoFTR 匹配（和 tracker_engine.py 一模一样）
        try:
            with torch.no_grad():
                dtype = torch.float16 if self.device.type == 'cuda' else torch.float32
                with torch.autocast(device_type=self.device.type, dtype=dtype):
                    output = self.loftr({"image0": mini_tensor, "image1": local_tensor})
        except Exception as e:
            logger.warning(f"LoFTR 异常: {e}")
            return self._last_pos

        k0 = output['keypoints0'].cpu().numpy()
        k1 = output['keypoints1'].cpu().numpy()
        conf = output['confidence'].cpu().numpy()

        # 5. 过滤 + 单应性（降低门槛提高匹配率）
        good = conf.flatten() > 0.2
        k0 = k0[good]
        k1 = k1[good]

        if len(k0) < 4:
            return self._last_pos  # 保持上次位置，不输出 warning

        M, mask = cv2.findHomography(k0, k1, cv2.RANSAC, 5.0)
        if M is None:
            logger.warning("LoFTR 单应性失败")
            return self._last_pos

        # 6. 变换中心点 → 大地图坐标
        center = np.float32([[[w / 2, h / 2]]])
        pos = cv2.perspectiveTransform(center, M)
        fx, fy = float(pos[0][0][0]) + x1, float(pos[0][0][1]) + y1

        inlier = np.sum(mask) / len(mask)
        if inlier < 0.15:
            logger.warning(f"LoFTR 内点不足: {inlier:.2f}")
            return self._last_pos

        self._last_pos = (fx, fy)
        return self._last_pos

    @property
    def loaded(self):
        return True
