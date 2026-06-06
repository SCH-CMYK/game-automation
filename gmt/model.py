import torch
import torch.nn as nn
from torchvision.models import mobilenet_v3_small, MobileNet_V3_Small_Weights


class MapTrackerNet(nn.Module):
    def __init__(self):
        super().__init__()
        # 1. 加载预训练的轻量化骨干网络
        self.backbone = mobilenet_v3_small(weights=MobileNet_V3_Small_Weights.DEFAULT)

        # 2. 修改最后的分类头，改为输出 2 个坐标值 (X, Y)
        in_features = self.backbone.classifier[3].in_features
        self.backbone.classifier[3] = nn.Sequential(
            nn.Linear(in_features, 2),
            nn.Sigmoid()  # 使用 Sigmoid 强制让输出值在 0.0 到 1.0 之间
        )

    def forward(self, x):
        return self.backbone(x)