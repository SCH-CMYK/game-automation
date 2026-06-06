import cv2
import numpy as np
import random
import os


def add_radar_fan_noise(img):
    """
    终极动态抗干扰：模拟随视角转动的半透明扇形视野范围 (纯白)
    """
    h, w = img.shape[:2]
    center = (w // 2, h // 2)
    # 扇形半径，足够覆盖到小地图边缘
    radius = int(max(w, h) * 0.8)

    start_angle = random.randint(0, 360)
    sweep_angle = random.randint(45, 120)  # 视野角度
    end_angle = start_angle + sweep_angle

    overlay = img.copy()
    # 纯白色的扇形
    fan_color = (255, 255, 255)

    cv2.ellipse(overlay, center, (radius, radius), 0, start_angle, end_angle, fan_color, -1)

    # 半透明混合 (透明度在 15% 到 40% 之间波动)
    alpha = random.uniform(0.15, 0.40)
    cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0, img)

    return img


def generate_training_data(big_map_path, num_samples=20000):
    # 1. 原汁原味读取 PNG
    big_map_raw = cv2.imread(big_map_path, cv2.IMREAD_UNCHANGED)
    if big_map_raw is None:
        raise FileNotFoundError(f"找不到地图文件：{big_map_path}")

    h, w = big_map_raw.shape[:2]

    # 🌟 核心修改 1：目标输入尺寸改为 180
    target_size = 180

    print("正在分析大地图的 PNG 图像结构...")

    if len(big_map_raw.shape) == 3 and big_map_raw.shape[2] == 4:
        alpha_channel = big_map_raw[:, :, 3]
        _, valid_mask = cv2.threshold(alpha_channel, 1, 255, cv2.THRESH_BINARY)
        big_map = cv2.cvtColor(big_map_raw, cv2.COLOR_BGRA2BGR)
    else:
        big_map = big_map_raw.copy()
        bg_color = big_map[0, 0]
        bg_mask = cv2.inRange(big_map, bg_color, bg_color)
        valid_mask = cv2.bitwise_not(bg_mask)

    print("全局有效区域扫描完成！")

    # 预加载干扰图标
    noise_icons = []
    icon_dir = "noise_icons"
    if os.path.exists(icon_dir):
        print(f"正在从 {icon_dir} 加载真实干扰图标...")
        for filename in os.listdir(icon_dir):
            if filename.lower().endswith('.png'):
                icon_path = os.path.join(icon_dir, filename)
                icon = cv2.imread(icon_path, cv2.IMREAD_UNCHANGED)
                if icon is not None and icon.shape[2] == 4:
                    noise_icons.append(icon)
        print(f"✅ 成功加载了 {len(noise_icons)} 个完美的透明干扰图标！")

    os.makedirs("train_data", exist_ok=True)
    labels = []
    generated_count = 0

    print(f"开始生成数据 (尺寸: {target_size}x{target_size}, 甜甜圈遮罩)...")

    while generated_count < num_samples:
        # 裁剪尺寸适配 180，随机范围改为 120~180
        current_crop_size = random.randint(120, 180)
        half_size = current_crop_size // 2

        cx = random.randint(half_size, w - half_size - 1)
        cy = random.randint(half_size, h - half_size - 1)

        x1, y1 = cx - half_size, cy - half_size
        x2, y2 = x1 + current_crop_size, y1 + current_crop_size

        crop_mask = valid_mask[y1:y2, x1:x2]
        valid_ratio = np.count_nonzero(crop_mask) / (current_crop_size * current_crop_size)

        if valid_ratio < 0.98:
            continue

        crop = big_map[y1:y2, x1:x2].copy()

        gray_crop = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        if np.std(gray_crop) < 5.0 or np.count_nonzero(cv2.Canny(gray_crop, 50, 150)) < 20:
            continue

        # 1. 统一缩放到 180x180
        crop = cv2.resize(crop, (target_size, target_size), interpolation=cv2.INTER_LINEAR)

        # 2. 🌟 核心修改 2：加入随机的视角扇形干扰 (50% 概率)
        if random.random() > 0.5:
            crop = add_radar_fan_noise(crop)

        # 3. 加入透明 UI 图标干扰
        if noise_icons:
            num_add_icons = random.randint(0, 5)
            for _ in range(num_add_icons):
                icon = random.choice(noise_icons)
                scale = random.uniform(0.5, 1.2)
                icon_h = max(5, int(icon.shape[0] * scale))
                icon_w = max(5, int(icon.shape[1] * scale))
                icon_resized = cv2.resize(icon, (icon_w, icon_h), interpolation=cv2.INTER_LINEAR)

                if target_size > icon_w and target_size > icon_h:
                    paste_x = random.randint(0, target_size - icon_w)
                    paste_y = random.randint(0, target_size - icon_h)

                    roi = crop[paste_y:paste_y + icon_h, paste_x:paste_x + icon_w]
                    icon_bgr = icon_resized[:, :, :3]
                    icon_alpha = icon_resized[:, :, 3] / 255.0

                    for c in range(3):
                        roi[:, :, c] = (icon_alpha * icon_bgr[:, :, c] + (1.0 - icon_alpha) * roi[:, :, c])

                    crop[paste_y:paste_y + icon_h, paste_x:paste_x + icon_w] = roi

        # 4. 🌟 核心修改 3：施加甜甜圈遮罩 (Donut Mask)
        # 注意：不再画方形黑框，直接用圆环切除废料
        donut_mask = np.zeros((target_size, target_size), dtype=np.uint8)
        center_x, center_y = target_size // 2, target_size // 2

        outer_radius = target_size // 2  # 180 / 2 = 90
        inner_radius = 15  # 中心盲区

        cv2.circle(donut_mask, (center_x, center_y), outer_radius, 255, -1)
        cv2.circle(donut_mask, (center_x, center_y), inner_radius, 0, -1)

        # 套上遮罩！任何掉在边角或中心的 UI 图标、扇形都会被极其锋利地切掉
        crop = cv2.bitwise_and(crop, crop, mask=donut_mask)

        # 5. 随机模糊
        if random.random() > 0.5:
            crop = cv2.GaussianBlur(crop, (3, 3), 0)

        norm_x = cx / w
        norm_y = cy / h

        filename = f"train_data/img_{generated_count}.jpg"
        cv2.imwrite(filename, crop)
        labels.append(f"{filename},{norm_x},{norm_y}\n")

        generated_count += 1

        if generated_count % 1000 == 0:
            print(f"进度: {generated_count} / {num_samples}")

    with open("labels.txt", "w") as f:
        f.writelines(labels)
    print(f"✅ 成功生成 {num_samples} 张包含完美视角扇形与甜甜圈遮罩的极限对抗数据！")


if __name__ == "__main__":
    generate_training_data("big_map.png", num_samples=30000)