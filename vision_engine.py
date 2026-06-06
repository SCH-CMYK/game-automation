"""
视觉引擎 — 单一多类模型（一次推理检出全部）
"""
import os
import threading
import logging
from typing import Optional
import numpy as np

logger = logging.getLogger("gameauto.vision")


class YOLODetector:
    def __init__(self, model_path: str):
        from ultralytics import YOLO
        self.model = YOLO(model_path)
        self.names = self.model.names
        logger.info(f"Loaded: {os.path.basename(model_path)}")
        logger.info(f"         Classes: {self.names}")

    def detect(self, image, conf=0.3, iou=0.5):
        results = self.model(image, verbose=False, conf=conf, iou=iou)
        dets = []
        for r in results:
            if r.boxes is None:
                continue
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                cls_id = int(box.cls[0])
                dets.append({
                    "bbox": (x1, y1, x2, y2),
                    "center": ((x1 + x2) // 2, (y1 + y2) // 2),
                    "confidence": float(box.conf[0]),
                    "class": self.names.get(cls_id, str(cls_id)),
                    "area": (x2 - x1) * (y2 - y1),
                    "cls_id": cls_id,
                })
        return dets


class VisionEngine:
    """单模型多类别检测"""

    def __init__(self):
        self._detector = None
        self._lock = threading.Lock()
        self._class_map = {}  # cls_name -> cls_id

    def load(self, model_path: str):
        """加载一个多类模型"""
        if not os.path.exists(model_path):
            logger.warning(f"Model not found: {model_path}")
            return False
        with self._lock:
            self._detector = YOLODetector(model_path)
            # 建立类别名映射
            self._class_map = {name: i for i, name in self._detector.names.items()}
        return True

    @property
    def loaded(self) -> bool:
        return self._detector is not None

    @property
    def names(self) -> dict:
        return self._detector.names if self._detector else {}

    def detect_all(self, image: np.ndarray, conf=0.3, iou=0.5) -> dict:
        """一次推理，返回按类别分组的检测结果
        返回: {"ore": [...], "creature": [...], "obstacle": [...], "character": [...]}
        """
        if not self._detector:
            return {"ore": [], "creature": [], "obstacle": [], "character": []}
        with self._lock:
            all_dets = self._detector.detect(image, conf=conf, iou=iou)
        grouped = {"ore": [], "creature": [], "obstacle": [], "character": []}
        for d in all_dets:
            cls = d["class"]
            if cls in grouped:
                grouped[cls].append(d)
        return grouped

    def find_best_ore(self, image):
        dets = self.detect_all(image)["ore"]
        if not dets:
            return None
        h, w = image.shape[:2]
        cx, cy = w // 2, h // 2
        return min(dets, key=lambda d: (d["center"][0] - cx) ** 2 + (d["center"][1] - cy) ** 2)

    def is_path_blocked(self, image, threshold=1):
        obs = self.detect_all(image)["obstacle"]
        if not obs:
            return False
        h, w = image.shape[:2]
        cx, cy = w // 2, h // 2
        for o in obs:
            ox, oy = o["center"]
            if abs(ox - cx) < w * 0.2 and abs(oy - cy) < h * 0.2:
                return True
        return False
