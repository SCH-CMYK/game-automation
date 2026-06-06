"""
YOLO 模型训练模块 - 一键训练目标检测模型
"""
import os
import yaml
import logging
from pathlib import Path

logger = logging.getLogger("gameauto.trainer")


class YOLOTrainer:
    """YOLO 训练器封装"""

    def __init__(self, dataset_dir: str, model_size: str = "n"):
        """
        dataset_dir: 数据集根目录，需符合 YOLO 格式
        model_size: 'n'(nano), 's'(small), 'm'(medium), 'l'(large)
        """
        self.dataset_dir = Path(dataset_dir)
        self.model_size = model_size
        self.model = None
        self.metrics = None

    def create_dataset_yaml(self, classes: list, output_path: str = None):
        """
        根据数据集目录结构生成 data.yaml
        classes: ["ore", "character", "portal", ...]
        """
        if output_path is None:
            output_path = str(self.dataset_dir / "data.yaml")

        data = {
            "path": str(self.dataset_dir.resolve()),
            "train": "images/train",
            "val": "images/val",
            "nc": len(classes),
            "names": classes,
        }

        with open(output_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)

        return output_path

    def train(self, epochs: int = 50, imgsz: int = 640, batch: int = 16,
              device: str = "cpu", resume: bool = False):
        """
        开始训练
        device: "cpu" / "cuda" / "0" (第一块GPU)
        """
        from ultralytics import YOLO

        model_name = f"yolo11{self.model_size}.pt"
        self.model = YOLO(model_name)

        data_yaml = str(self.dataset_dir / "data.yaml")
        if not os.path.exists(data_yaml):
            train_images = self.dataset_dir / "images" / "train"
            if not train_images.exists():
                raise FileNotFoundError(
                    f"数据集路径不正确，请确保存在 {train_images}\n"
                    f"数据集结构应为:\n"
                    f"  {self.dataset_dir}/\n"
                    f"    images/\n"
                    f"      train/  (训练图片)\n"
                    f"      val/    (验证图片)\n"
                    f"    labels/\n"
                    f"      train/  (标注文件 .txt)\n"
                    f"      val/    (标注文件 .txt)"
                )
            label_dir = self.dataset_dir / "labels" / "train"
            class_ids = set()
            for f in label_dir.glob("*.txt"):
                with open(f) as fh:
                    for line in fh:
                        parts = line.strip().split()
                        if parts:
                            class_ids.add(int(parts[0]))
            classes = [f"class_{i}" for i in sorted(class_ids)]
            self.create_dataset_yaml(classes, data_yaml)
            logger.info("自动生成 data.yaml，类别: %s", classes)

        results = self.model.train(
            data=data_yaml,
            epochs=epochs,
            imgsz=imgsz,
            batch=batch,
            device=device,
            resume=resume,
            verbose=True,
            workers=0,
            amp=True,
            cos_lr=True,
            close_mosaic=10,
            cache='disk',
            val=False,          # 关验证省显存，3050Ti 4GB 验证时会爆
        )
        self.metrics = results
        return results

    def export_best(self, output_dir: str, search_dir: str = None, name: str = "best"):
        """导出最佳模型
        output_dir: 导出目标目录
        search_dir: 搜索训练结果的根目录
        name: 自定义模型文件名（不带扩展名），默认 best
        """
        root = Path(search_dir) if search_dir else Path(__file__).parent.parent.parent.resolve()
        runs_dir = root / "runs" / "detect"
        train_dirs = sorted(runs_dir.glob("train*"), key=lambda p: p.stat().st_mtime, reverse=True)
        best_pt = train_dirs[0] / "weights" / "best.pt" if train_dirs else None

        if not best_pt or not best_pt.exists():
            raise FileNotFoundError(f"未找到训练好的模型: {best_pt}")

        import shutil
        os.makedirs(output_dir, exist_ok=True)
        dest = os.path.join(output_dir, f"{name}.pt")
        shutil.copy(best_pt, dest)
        logger.info("模型已导出到: %s", dest)
        return dest


def create_dataset_structure(root_dir: str, classes: list):
    """
    快速创建 YOLO 数据集目录结构
    root_dir/
      images/train/
      images/val/
      labels/train/
      labels/val/
      data.yaml
    """
    root = Path(root_dir)
    for split in ["train", "val"]:
        (root / "images" / split).mkdir(parents=True, exist_ok=True)
        (root / "labels" / split).mkdir(parents=True, exist_ok=True)

    trainer = YOLOTrainer(str(root))
    trainer.create_dataset_yaml(classes)
    logger.info("数据集目录已创建在: %s", root_dir)
    logger.info("  将训练图片放入 images/train/")
    logger.info("  将验证图片放入 images/val/")
    logger.info("  标注文件(.txt)放入对应的 labels/ 目录")


if __name__ == "__main__":
    # 示例用法
    import sys
    if len(sys.argv) > 1:
        create_dataset_structure(sys.argv[1], sys.argv[2:])
