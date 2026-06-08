# 模型文件目录

此目录存放 AI 模型文件。模型文件较大，不包含在 Git 仓库中。

## 自动下载

```bash
python download_models.py
```

## 手动下载

从 [GitHub Releases](https://github.com/SCH-CMYK/game-automation/releases/tag/v1.0) 下载以下文件放入此目录：

- `best_20260601.pt` — YOLO 检测模型 (~18 MB)
- `loftr_model.onnx` — LoFTR 定位模型 (~37 MB)

地图文件放入 `maps/` 目录：

- `big_map.png` — 游戏大地图 (~3 MB)
