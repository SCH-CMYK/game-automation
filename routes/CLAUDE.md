# Routes — 路线文件说明

## 格式

```json
{
  "waypoints": [
    [x, y, "name"],
    [100, 200, "起点"],
    [350, 180, "矿点A"],
    [500, 300, "终点"]
  ]
}
```

- 坐标: 地图图片上的像素坐标
- name: 途经点标签（用于 GUI 显示）
- 途经点按顺序走, 到达后采矿（duration 在 route_planner 中配置）

## 目录结构

```
routes/
├── diquluxian/    # 地曲路线
├── zhiwu/         # 植物采集路线
└── qita/          # 其他路线
```

## 使用方式

1. 在 main.py 的路线规划标签页中加载路线
2. route_planner 读取 waypoints → SIFT 定位当前位置 → 逐个导航
3. 到达途经点自动开始采矿（automator.walk_to_mine）

## 注意事项
- 路线坐标绑定特定地图（maps/big_map.png），换了地图需要重新绘制
- 地图更新后（游戏版本更新），旧路线坐标可能偏移
