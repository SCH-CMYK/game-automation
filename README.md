# GameAuto — AI 游戏助手

**洛克王国世界 自动导航 + 采矿工具**

> ⚠️ 本工具仅用于**学习研究**目的，完全免费。
> **禁止售卖、禁止用于商业用途、禁止用于破坏游戏公平性。**

---

## 环境要求

- Windows 10/11
- Python 3.10+
- NVIDIA 显卡 (2GB+ VRAM，至少 RTX 3050)
- 管理员权限（热键需要）

## 安装

```bash
cd D:\game-automation
pip install -r requirements.txt
```

## 快速开始

### 1. 启动程序
```bash
# 管理员运行
python main.py
# 或双击 run.bat
```

### 2. 加载模型
- 侧边栏选择 `best_20260601.pt`
- 点击「加载模型」

### 3. 导航
- 切换到「路线规划」标签页
- 大地图自动加载
- 左键点击添加途经点
- 右键删除途经点
- 滚轮缩放、拖拽移动
- 点击「加载路线」选择已有路线
- 点击「开始导航」

## 操作说明

| 功能 | 操作 |
|------|------|
| 地图缩放 | 鼠标滚轮 |
| 地图移动 | 拖拽 |
| 添加途经点 | 左键点击 |
| 删除途经点 | 右键点击 |
| 保存路线 | 「保存路线」按钮 |
| 加载路线 | 「加载路线」按钮 |
| 开始导航 | 「开始导航」按钮 |
| 紧急停止 | Ctrl+Shift+Q |
| 截图 | Ctrl+L |
| 计时截图 | Ctrl+T |

## 功能

- **自动导航**: LoFTR 小地图定位 + 途经点跟随
- **自动采矿**: YOLO 实时检测矿石，自动瞄准采集
- **战斗逃跑**: 检测到战斗自动退出
- **路线编辑**: 可视化编辑和保存路线

## 项目结构

```
game-automation/
├── main.py              GUI 主程序
├── route_planner.py     导航引擎
├── hybrid_positioner.py LoFTR 定位
├── automator.py         采矿状态机
├── controller.py        键鼠控制(Interception驱动)
├── vision_engine.py     YOLO 检测
├── screen_capture.py    屏幕截图
├── hotkey.py            全局热键
├── minimap_detector.py  小地图检测(霍夫圆)
├── config.py            配置参数
├── trainer.py           YOLO 训练
├── label_tool.py        数据标注
├── logger.py            日志系统
├── models/              模型文件
├── routes/              路线文件
├── maps/                大地图
├── tests/               测试
├── logs/                日志
└── archive/             已弃用代码
```

## 模型下载

模型文件较大，需单独下载（放入 `models/` 目录）：

| 文件 | 用途 | 大小 | 下载 |
|------|------|------|------|
| `best_20260601.pt` | YOLO 矿石/精灵/障碍物/角色检测 | 18 MB | [⬇ 下载](https://github.com/SCH-CMYK/game-automation/releases/download/v1.0/best_20260601.pt) |
| `loftr_model.onnx` | LoFTR 小地图特征匹配 | 37 MB | [⬇ 下载](https://github.com/SCH-CMYK/game-automation/releases/download/v1.0/loftr_model.onnx) |
| `big_map.png` | 游戏大地图 (8192×8192) | 3 MB | [⬇ 下载](https://github.com/SCH-CMYK/game-automation/releases/download/v1.0/big_map.png) |

> 下载后放入对应目录：`.pt` 和 `.onnx` → `models/`，`.png` → `maps/`

## 常见问题

**热键不生效**: 管理员运行 `run.bat`

**导航不动**: 检查小地图区域是否正确（点「框选小地图」重新选）

**采矿不准**: 调整 `config.py` 中的 MiningConfig 参数

---

## 声明

本项目**仅用于学习和研究**人工智能、计算机视觉、自动化技术。

- ❌ 禁止用于商业用途
- ❌ 禁止售卖本工具
- ❌ 禁止破坏游戏公平性
- ❌ 使用本工具产生的任何后果由使用者自行承担

**请尊重游戏开发者，合理使用自动化工具。**
