# GMT (Game-Map-Tracker) 集成

## 来源
- 项目: [Game-Map-Tracker](https://github.com/761696148/Game-Map-Tracker)
- 洛克王国专用小地图定位工具
- 提供 SIFT 匹配参数、地图图片、路线管理器

## 关键文件

| 文件 | 用途 |
|------|------|
| `config.json` | SIFT 参数 + 地图路径 + 小地图区域坐标 |
| `selector.py` | 小地图区域选取工具 |
| `tracker_engine.py` | 核心追踪引擎 |
| `route_manager.py` | 路线点管理 |
| `download_map.py` | 地图下载 |
| `dataset_generator.py` | 训练数据生成 |
| `main_sift.py` / `main_hybrid.py` / `main_ai.py` | GMT 自带入口（本项目不直接用） |

## 配置流向

```
gmt/config.json
    ↓ sift_config.py 读取
    ├── SIFT_MATCH_RATIO (默认 0.9)
    ├── SIFT_MIN_MATCH_COUNT (默认 5)
    ├── LOGIC_MAP_PATH → maps/big_map.png
    ├── DISPLAY_MAP_PATH → maps/big_map-1.png
    └── MINIMAP {top, left, width, height}
            ↓ route_planner.py 使用
            SIFT 特征匹配 + 黄色箭头定位
```

## 注意事项
- GMT 配置里的坐标是屏幕绝对坐标, 不同分辨率需重新校准
- `MINIMAP` 区域坐标在 `sift_config.py` 中映射为 `minimap_region`
- 修改 GMT 参数后需重启程序, sift_config 在 import 时读取
- GMT 自带的 main_*.py 文件仅供参考, 本项目用 route_planner.py 替代
