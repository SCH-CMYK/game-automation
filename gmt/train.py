import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from torchvision import transforms
# 【改动 1】：引入参数量更大的 ResNet18
from torchvision.models import resnet50, ResNet50_Weights
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights
from torchvision.models import resnet18, ResNet18_Weights
import cv2
import os
import time
import numpy as np
# ==========================================
# 🌟 新增：动态生成 2D 高斯热力图
# ==========================================
def generate_gaussian_heatmap(size, cx, cy, sigma=3.0):
    """
    生成一张二维高斯热力图
    :param size: 热力图的尺寸 (例如 64，表示 64x64 的矩阵)
    :param cx: 目标的 X 坐标 (归一化 0~1)
    :param cy: 目标的 Y 坐标 (归一化 0~1)
    :param sigma: 高斯斑的半径大小 (推荐 2.0 ~ 3.0)
    """
    # 将 0~1 的归一化坐标转换为热力图上的实际像素坐标
    center_x = cx * size
    center_y = cy * size

    # 创建网格坐标
    x = np.arange(0, size, 1, np.float32)
    y = np.arange(0, size, 1, np.float32)
    X, Y = np.meshgrid(x, y)

    # 套用二维高斯函数公式
    heatmap = np.exp(-((X - center_x) ** 2 + (Y - center_y) ** 2) / (2 * sigma ** 2))

    return torch.tensor(heatmap, dtype=torch.float32).unsqueeze(0)  # 增加通道维度变为 (1, H, W)
# ==========================================
# 1. 定义数据加载器 (告诉 PyTorch 怎么读取你的图片和标签)
# ==========================================
class MapDataset(Dataset):
    def __init__(self, label_file):
        self.data = []
        with open(label_file, 'r') as f:
            for line in f:
                parts = line.strip().split(',')
                if len(parts) == 3:
                    img_path, norm_x, norm_y = parts[0], float(parts[1]), float(parts[2])
                    self.data.append((img_path, norm_x, norm_y))
        print(f"📦 成功加载数据集，共 {len(self.data)} 张图片。")
        self.transform = transforms.Compose([
            transforms.ToTensor(),
            # 无论图片多大，训练前统一压成 150x150
            transforms.Resize((150, 150), antialias=True),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        # 定义 AI 输出的热力图分辨率 (64x64 是精度和性能的完美平衡)
        self.heatmap_size = 64

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx):
        img_path, nx, ny = self.data[idx]

        img = cv2.imread(img_path)
        if img is None:
            raise ValueError(f"读取图片失败: {img_path}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img_tensor = self.transform(img)

        # 🌟 核心改动：不再生成一维坐标 Tensor，而是生成一张 64x64 的热力图！
        target_heatmap = generate_gaussian_heatmap(self.heatmap_size, nx, ny, sigma=2.5)

        return img_tensor, target_heatmap


# ==========================================
# 2. 定义轻量化神经网络 (MobileNetV3-Small 热力图版)
# ==========================================
# class HeatmapTrackerNet(nn.Module):
#     def __init__(self, heatmap_size=64):
#         super().__init__()
#         self.heatmap_size = heatmap_size
#
#         # 加载带预训练权重的轻量化骨干网络 (参数量仅 250 万)
#         self.backbone = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT)
#
#         # 获取 MobileNetV3 分类器的输入特征维度 (通常是 576)
#         in_features = self.backbone.classifier[0].in_features
#
#         # 🌟 核心改动：彻底覆盖原本的 classifier，输出 4096 个节点并加上 Sigmoid
#         self.backbone.classifier = nn.Sequential(
#             nn.Linear(in_features, self.heatmap_size * self.heatmap_size),
#             nn.Sigmoid()
#         )
#
#     def forward(self, x):
#         x = self.backbone(x)
#         # 将扁平的 4096 向量，重新折叠成 (Batch_size, 1通道, 64高度, 64宽度) 的热力图
#         return x.view(-1, 1, self.heatmap_size, self.heatmap_size)
# class HeatmapTrackerNet(nn.Module):
#     def __init__(self):
#         super().__init__()
#         self.backbone = resnet50(weights=ResNet50_Weights.DEFAULT)
#         in_features = self.backbone.fc.in_features
#
#         self.heatmap_size = 64
#
#         # 🌟 核心改动：输出 4096 个节点，并加上 Sigmoid 把亮度限制在 0.0 ~ 1.0 之间
#         self.backbone.fc = nn.Sequential(
#             nn.Linear(in_features, self.heatmap_size * self.heatmap_size),
#             nn.Sigmoid()
#         )
#
#     def forward(self, x):
#         x = self.backbone(x)
#         # 🌟 核心改动：将扁平的 4096 向量，重新折叠成 (Batch_size, 1通道, 64高度, 64宽度) 的热力图
#         return x.view(-1, 1, 64, 64)
# ==========================================
# 2. 定义中量级神经网络 (ResNet18 热力图版)
# ==========================================
class HeatmapTrackerNet(nn.Module):
    def __init__(self, heatmap_size=64):
        super().__init__()
        self.heatmap_size = heatmap_size

        # 加载 ResNet18 骨干网络 (参数量约 1100 万，性能与速度的完美平衡)
        self.backbone = resnet18(weights=ResNet18_Weights.DEFAULT)

        # 获取 ResNet18 全连接层的输入特征维度 (512)
        in_features = self.backbone.fc.in_features

        # 彻底覆盖原本的 fc 层，输出 4096 个节点并加上 Sigmoid
        self.backbone.fc = nn.Sequential(
            nn.Linear(in_features, self.heatmap_size * self.heatmap_size),
            nn.Sigmoid()
        )

    def forward(self, x):
        x = self.backbone(x)
        # 将扁平的 4096 向量，重新折叠成 (Batch_size, 1通道, 64高度, 64宽度) 的热力图
        return x.view(-1, 1, self.heatmap_size, self.heatmap_size)
# ==========================================
# 3. 核心训练引擎
# ==========================================
def train_model():
    # 检测计算设备：有 N 卡就用 CUDA 狂飙，没有就用 CPU 慢慢算
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"🚀 当前使用的训练设备: {device}")

    # 超参数设置
    batch_size = 32  # 每次喂给显卡 32 张图片 (如果报错显存不足 OOM，改小成 16 或 8)
    learning_rate = 3e-4  # 【核心修改 2】：稍微调大学习率，帮模型冲破早期的迷茫期
    epochs = 30  # 总共把所有数据学多少遍

    # 加载数据
    dataset = MapDataset("labels.txt")
    dataloader = DataLoader(dataset, batch_size=batch_size, shuffle=True, num_workers=4 if os.name != 'nt' else 0)

    # 实例化模型并丢进显卡
    model = HeatmapTrackerNet().to(device)

    # 【核心修改 3】：更换为 L1Loss (平均绝对误差)。误差是 0.1，Loss 就是 0.1，逼迫模型像素级对齐！
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=1e-4)

    print("\n🔥 开始训练！(可能需要十几分钟到半小时，请耐心等待)")
    best_loss = float('inf')

    # 开始 Epoch 循环
    for epoch in range(epochs):
        model.train()  # 开启训练模式
        running_loss = 0.0
        start_time = time.time()

        # 开始 Batch 循环
        for i, (inputs, targets) in enumerate(dataloader):
            inputs, targets = inputs.to(device), targets.to(device)

            # 1. 梯度清零
            optimizer.zero_grad()
            # 2. 前向传播 (让 AI 猜坐标)
            outputs = model(inputs)
            # 3. 计算误差
            loss = criterion(outputs, targets)
            # 4. 反向传播 (告诉 AI 错在哪)
            loss.backward()
            # 5. 更新权重 (AI 变聪明了一点点)
            optimizer.step()

            running_loss += loss.item()

            # 每 100 个批次打印一次进度
            if (i + 1) % 100 == 0:
                print(f"  Epoch [{epoch + 1}/{epochs}], Step [{i + 1}/{len(dataloader)}], Loss: {loss.item():.6f}")

                # [反向解析热力图]：找到预测热力图上最亮那个点的坐标
                pred_heatmap = outputs[0][0].detach().cpu().numpy()
                real_heatmap = targets[0][0].cpu().numpy()

                # 找到最亮像素的索引 (Y, X)
                pred_y, pred_x = np.unravel_index(np.argmax(pred_heatmap), pred_heatmap.shape)
                real_y, real_x = np.unravel_index(np.argmax(real_heatmap), real_heatmap.shape)

                # 换算回归一化坐标
                p_nx, p_ny = pred_x / 64.0, pred_y / 64.0
                r_nx, r_ny = real_x / 64.0, real_y / 64.0

                print(f"  🎯 [监控] 真实坐标: ({r_nx:.3f}, {r_ny:.3f}) | AI预测: ({p_nx:.3f}, {p_ny:.3f})")

        # 计算这一遍学习的平均误差
        epoch_loss = running_loss / len(dataloader)
        epoch_time = time.time() - start_time
        print(f"✅ Epoch [{epoch + 1}/{epochs}] 完成! 平均 Loss: {epoch_loss:.6f}, 耗时: {epoch_time:.1f} 秒")

        # ==========================================
        # 4. 保存最聪明的模型大脑
        # ==========================================
        if epoch_loss < best_loss:
            best_loss = epoch_loss
            torch.save(model.state_dict(), "best_tracker_model.pth")
            print(f"   🌟 发现更优模型！已保存为 best_tracker_model.pth")

    print(f"\n🎉 训练彻底结束！最终最佳 Loss: {best_loss:.6f}")
    print(f"你的专属 AI 模型已经诞生，文件名为：best_tracker_model.pth")


if __name__ == "__main__":
    train_model()