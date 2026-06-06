# GameAuto Project

## Quick Start
```bash
python main.py           # GUI
python -m pytest tests/  # Tests
```

## Core Files
| File | Purpose |
|------|---------|
| main.py | GUI, route editing |
| route_planner.py | Navigation, battle escape, ore mining |
| hybrid_positioner.py | Kornia LoFTR minimap positioning |
| automator.py | Mining state machine |
| controller.py | Interception driver input |
| vision_engine.py | YOLO detection |
| config.py | All config parameters |
| minimap_detector.py | HoughCircles detection |

## Navigation Architecture
```
Frame → HoughCircles → LoFTR position → Turn calculation → Walk
         (battle check)   (tracking)     (actual vs desired)
```

## Key Parameters (config.py)
- Mining: MINING.mine_hold_duration, mine_cooldown
- Route: ROUTE.arrive_threshold_px
- AI: AI.model_path

## Models
- YOLO: best_20260601.pt (ore/creature/obstacle/character)
- LoFTR: loftr_model.onnx (feature matching)
- Map: big_map.png (8192x8192)
