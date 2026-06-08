# GameAuto Project

## Quick Start
```bash
python main.py           # GUI
python -m pytest tests/  # Tests
```

## Architecture

```
src/
├── engine/          # Low-level: capture, vision, input, positioning
│   ├── controller.py
│   ├── screen_capture.py
│   ├── vision_engine.py      (YOLO)
│   ├── hybrid_positioner.py  (LoFTR)
│   ├── minimap_detector.py   (HoughCircles)
│   └── minimap_selector.py
├── automation/      # High-level: mining, navigation, teleport, hotkeys
│   ├── automator.py
│   ├── route_planner.py
│   ├── teleporter.py
│   └── hotkey.py
├── training/        # YOLO training + labeling
│   ├── trainer.py
│   └── label_tool.py
└── utils/           # Config, logging, converters
    ├── config.py
    ├── logger.py
    └── ...
main.py              # Entry point (GUI)
```

## Navigation Pipeline

```
Frame → HoughCircles → LoFTR position → Turn calculation → Walk
         (battle check)   (tracking)     (actual vs desired)
```

## Route Format

`routes/*.json` — waypoint arrays in map pixel coordinates:
```json
{"waypoints": [[x, y, "name"], ...]}
```

## Key Config (src/utils/config.py)

- Mining: `MINING.mine_hold_duration`, `mine_cooldown`
- Route: `ROUTE.arrive_threshold_px`
- AI: `AI.model_path`

## Config Flow

```
gmt/config.json (SIFT params + map path)
    ↓ sift_config.py
    ├── SIFT_MATCH_RATIO, MINIMAP area
    └── maps/big_map.png (8192×8192)
```

## Models

- YOLO: best_20260601.pt (ore/creature/obstacle/character)
- LoFTR: loftr_model.onnx (feature matching)
- Map: big_map.png (8192×8192)

## GMT Sub-project

`gmt/` is a reference implementation (Game-Map-Tracker). Not used directly — `route_planner.py` replaces it. Key files: `config.json` (SIFT params), `tracker_engine.py` (LoFTR engine).
