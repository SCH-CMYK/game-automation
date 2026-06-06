# Archive

此目录保存了从项目中移除的旧模块。它们不再被任何代码引用，但保留了先前的开发成果以供参考。

## navigator.py
- **原因**: import 已损坏 — `from vision import TemplateMatcher`（`vision.py` 文件不存在）
- **原用途**: 基于模板匹配和颜色识别的导航引擎（旧版方案，已被 SIFT-based `route_planner.py` 替代）
- **移除日期**: 2026-06-02
- **注意**: 如果将来需要非 SIFT 的导航方案（如颜色追踪），其中的 `MapAnalyzer` 和 `MinimapTracker` 类可能有参考价值

## minimap.py
- **原因**: 未被任何模块引用，CLAUDE.md 明确标注为"未使用"
- **原用途**: 在小地图上通过模板匹配寻找矿石图标的导航辅助
- **移除日期**: 2026-06-02
- **注意**: `find_ore_on_minimap` 方法有逻辑 bug（取第一个通过阈值的匹配而非最高置信度），如要复用需修正
