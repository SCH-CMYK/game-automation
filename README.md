# GameAuto — AI 游戏助手

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python">
  <img src="https://img.shields.io/badge/license-CC%20BY--NC%204.0-green.svg" alt="License">
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-lightgrey.svg" alt="Platform">
  <img src="https://img.shields.io/badge/test-48%20passed-brightgreen.svg" alt="Tests">
</p>

**洛克王国世界 自动导航 + 自动采矿工具**

> ⚠️ 本工具仅用于**学习研究**目的，完全免费。
> **禁止售卖、禁止用于商业用途、禁止用于破坏游戏公平性。**

---

## 功能

| 功能 | 技术 | 说明 |
|------|------|------|
| 自动导航 | LoFTR 特征匹配 | 小地图实时定位 + 途经点跟随 |
| 自动采矿 | YOLO 实时检测 | 检测矿石 → 瞄准 → 采集 → 下一目标 |
| 战斗逃跑 | 霍夫圆检测 | 小地图消失 = 进入战斗 → 自动退出 |
| 路线编辑 | CustomTkinter | 可视化地图上添加/删除/保存途经点 |
| 数据标注 | 内置标注工具 | 收集训练数据，训练自己的 YOLO 模型 |
| 全局热键 | Interception 驱动 | 内核级键鼠模拟，不修改游戏内存 |

---

## 环境要求

- **OS**: Windows 10/11
- **Python**: 3.10+
- **GPU**: NVIDIA 显卡 (2GB+ VRAM)
- **权限**: 管理员（Interception 驱动需要）

---

## 安装

```bash
git clone https://github.com/SCH-CMYK/game-automation.git
cd game-automation
pip install -r requirements.txt
```

或下载 ZIP + 双击 `setup.bat`

---

## 模型下载

模型和地图文件较大，从 Releases 下载后放入对应目录：

| 文件 | 用途 | 大小 | 下载 |
|------|------|------|------|
| `best_20260601.pt` | YOLO 检测模型 | 18 MB | [⬇ 下载](https://github.com/SCH-CMYK/game-automation/releases/download/v1.0/best_20260601.pt) |
| `loftr_model.onnx` | LoFTR 定位模型 | 37 MB | [⬇ 下载](https://github.com/SCH-CMYK/game-automation/releases/download/v1.0/loftr_model.onnx) |
| `big_map.png` | 游戏大地图 (8192×8192) | 3 MB | [⬇ 下载](https://github.com/SCH-CMYK/game-automation/releases/download/v1.0/big_map.png) |

```
models/
├── best_20260601.pt
└── loftr_model.onnx
maps/
└── big_map.png
```

---

## 安装 Interception 驱动 ⚠️ 必装

程序依赖 Interception 内核驱动来控制键鼠（非内存修改，反作弊安全）。

1. 下载 [Interception.zip](https://github.com/oblitum/Interception/releases/latest)
2. 解压，**以管理员身份运行 cmd**，进入解压目录
3. 执行安装：
   ```cmd
   install-interception.exe /install
   ```
4. **重启电脑**

> 安装后 `sc query interception` 看到 RUNNING 即成功

---

## 快速开始

```bash
# 管理员运行
python main.py
# 或双击 run.bat
```

1. 侧边栏加载 YOLO 模型
2. 切换到「路线规划」标签页
3. 大地图上左键添加途经点，右键删除
4. 点击「开始导航」

---

## 项目结构

```
game-automation/
├── main.py                 # 入口：GUI 主程序
├── src/
│   ├── engine/             # 底层引擎
│   │   ├── controller.py       # 键鼠控制 (Interception 驱动)
│   │   ├── screen_capture.py   # 屏幕截图
│   │   ├── vision_engine.py    # YOLO 实时检测
│   │   ├── hybrid_positioner.py# LoFTR 定位
│   │   ├── minimap_detector.py # 小地图检测 (霍夫圆)
│   │   └── minimap_selector.py # 手动框选小地图
│   ├── automation/         # 自动化逻辑
│   │   ├── automator.py        # 采矿状态机
│   │   ├── route_planner.py    # 导航引擎
│   │   ├── teleporter.py       # 传送
│   │   └── hotkey.py           # 全局热键
│   ├── training/           # 模型训练
│   │   ├── trainer.py          # YOLO 训练器
│   │   └── label_tool.py       # 数据标注工具
│   └── utils/              # 工具集
│       ├── config.py           # 配置中心
│       ├── logger.py           # 日志系统
│       └── ...                 # 转换器、内存读取等
├── gmt/                    # 地图追踪子项目
├── tests/                  # 测试 (48 通过)
├── models/                 # 模型文件 (需下载)
├── maps/                   # 大地图 (需下载)
├── routes/                 # 路线文件
├── datasets/               # 训练数据集
├── archive/                # 已弃用代码
├── templates/              # UI 图标
├── tools/                  # 附加工具
├── setup.bat               # 一键安装
├── run.bat                 # 一键启动
├── requirements.txt        # PyPI 依赖
├── LICENSE                 # CC BY-NC 4.0
└── README.md
```

---

## 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Ctrl + Shift + Q` | 紧急停止 |
| `Ctrl + L` | 截图 |
| `Ctrl + T` | 计时截图 |

---

## 运行测试

```bash
python -m pytest tests/ -v
```

---

## 声明

本项目**仅用于学习和研究**人工智能、计算机视觉、自动化技术。

- ❌ 禁止用于商业用途
- ❌ 禁止售卖本工具
- ❌ 禁止破坏游戏公平性
- ❌ 使用本工具产生的任何后果由使用者自行承担

**请尊重游戏开发者，合理使用自动化工具。**

---

## License

[CC BY-NC 4.0](LICENSE) — 署名-非商业使用 4.0 国际
