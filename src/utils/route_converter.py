"""
路线格式转换器 — 将 GMT 格式路线转为标准 waypoints 格式

GMT 格式（55条子目录路线）:
  {"name", "loop", "notes", "points": [{"x","y","label","radius"}, ...]}

标准格式（5条根路线，route_planner.py 使用）:
  {"waypoints": [[x, y, "name"], ...]}

用法:
  python route_converter.py              # 预览转换（不写入）
  python route_converter.py --commit     # 执行转换
  python route_converter.py --dedupe     # 检查并报告重复文件
"""
import json
import sys
import hashlib
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.parent.parent.resolve()
ROUTES_DIR = PROJECT_DIR / "routes"


def hash_file(path: Path) -> str:
    """计算文件内容的 MD5"""
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def detect_format(data: dict) -> str:
    """检测路线格式"""
    if "waypoints" in data:
        return "waypoints"
    elif "points" in data:
        return "points"
    return "unknown"


def convert_to_waypoints(data: dict) -> dict:
    """将 points 格式转为 waypoints 格式"""
    points = data.get("points", [])
    waypoints = []
    for i, p in enumerate(points, 1):
        x = p.get("x", 0)
        y = p.get("y", 0)
        label = p.get("label", f"点{i}")
        waypoints.append([x, y, label])

    result = {"waypoints": waypoints}

    # 保留元信息
    if "name" in data:
        result["name"] = data["name"]
    if "loop" in data:
        result["loop"] = data["loop"]
    if "notes" in data:
        result["notes"] = data["notes"]

    return result


def find_duplicates() -> dict:
    """按内容哈希分组，找出重复文件"""
    hashes = {}
    for f in sorted(ROUTES_DIR.glob("**/*.json")):
        h = hash_file(f)
        if h not in hashes:
            hashes[h] = []
        hashes[h].append(str(f.relative_to(ROUTES_DIR)))
    return {h: files for h, files in hashes.items() if len(files) > 1}


def main():
    commit = "--commit" in sys.argv
    dedupe = "--dedupe" in sys.argv

    if dedupe:
        dups = find_duplicates()
        if dups:
            print("=== 重复文件（内容相同）===")
            for h, files in dups.items():
                print(f"  MD5: {h[:12]}...")
                for f in files:
                    print(f"    - {f}")
                print()
        else:
            print("未发现重复文件。")
        return

    print(f"扫描路线目录: {ROUTES_DIR}")
    print()

    converted = 0
    skipped = 0
    total = 0

    for f in sorted(ROUTES_DIR.glob("**/*.json")):
        total += 1
        rel = f.relative_to(ROUTES_DIR)

        try:
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            print(f"  [错误] {rel}: JSON 解析失败 — {e}")
            continue

        fmt = detect_format(data)
        if fmt == "waypoints":
            print(f"  [跳过] {rel}: 已是标准格式")
            skipped += 1
        elif fmt == "points":
            wp_count = len(data.get("points", []))
            if commit:
                new_path = ROUTES_DIR / f.parent.name / f"{f.stem}_converted.json"
                new_data = convert_to_waypoints(data)
                with open(new_path, "w", encoding="utf-8") as fh:
                    json.dump(new_data, fh, indent=2, ensure_ascii=False)
                print(f"  [转换] {rel} → {new_path.relative_to(ROUTES_DIR)} ({wp_count} 个途经点)")
            else:
                print(f"  [预览] {rel}: {wp_count} 个途经点 → 将转为 waypoints 格式")
            converted += 1
        else:
            print(f"  [未知] {rel}: 无法识别的格式 (keys: {list(data.keys())})")
            skipped += 1

    print()
    print(f"总计: {total} 个文件, {converted} 个待转换, {skipped} 个跳过")

    if not commit:
        print()
        print("预览模式 — 未写入文件。使用 --commit 执行转换。")
        print("python route_converter.py --commit")
        print()
        print("检查重复文件:")
        print("python route_converter.py --dedupe")


if __name__ == "__main__":
    main()
