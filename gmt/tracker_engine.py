import cv2
import numpy as np
import torch
import kornia as K
from kornia.feature import LoFTR

class LoftrEngine:
    def __init__(self, device):
        self.device = device
        # 换回 outdoor 稳定性更高
        self.matcher = LoFTR(pretrained='outdoor').to(self.device)
        self.matcher.eval()

    def preprocess(self, img_bgr):
        img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
        h, w = img_gray.shape
        new_h, new_w = h - (h % 8), w - (w % 8)
        img_gray = cv2.resize(img_gray, (new_w, new_h))
        tensor = K.image_to_tensor(img_gray, False).float() / 255.0
        return tensor.to(self.device)

    def match(self, mini_tensor, local_tensor):
        with torch.no_grad():
            with torch.autocast(device_type='cuda', dtype=torch.float16):
                return self.matcher({"image0": mini_tensor, "image1": local_tensor})