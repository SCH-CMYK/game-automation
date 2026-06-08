"""
Auto-download model and map files from GitHub Releases.
Usage: python download_models.py
"""

import sys
import urllib.request
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
MODELS_DIR = PROJECT_DIR / "models"
MAPS_DIR = PROJECT_DIR / "maps"

FILES = {
    "best_20260601.pt": {
        "dir": MODELS_DIR,
        "desc": "YOLO detection model",
        "size": 19_161_683,
    },
    "loftr_model.onnx": {
        "dir": MODELS_DIR,
        "desc": "LoFTR positioning model",
        "size": 39_295_679,
    },
    "big_map.png": {
        "dir": MAPS_DIR,
        "desc": "Game world map (8192x8192)",
        "size": 3_458_022,
    },
}

RELEASE_URL = (
    "https://github.com/SCH-CMYK/game-automation/releases/download/v1.0"
)


def _download(url: str, dest: Path, desc: str) -> bool:
    """Download a single file with progress bar. Returns True on success."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    print(f"\n  >> {desc}")
    print(f"     {url}")

    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "game-auto-downloader"}
        )
        with urllib.request.urlopen(req) as resp:
            total = resp.headers.get("Content-Length")
            total = int(total) if total else 0

            downloaded = 0
            block_size = 8192
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(block_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = downloaded * 100 // total
                        bar = "#" * (pct // 5) + "-" * (20 - pct // 5)
                        print(
                            f"\r    [{bar}] {pct:3d}%  "
                            f"{downloaded / 1024 / 1024:.1f}MB",
                            end="",
                            flush=True,
                        )
                if total:
                    print()
        return True
    except Exception as e:
        print(f"\n    FAIL: {e}")
        return False


def check_file(name: str, info: dict) -> str | None:
    """Check if a file exists and has the expected size.
    Returns None if OK, or an error string."""
    path = info["dir"] / name
    if not path.exists():
        return "missing"
    actual = path.stat().st_size
    expected = info["size"]
    if abs(actual - expected) > 1024 * 100:  # 100KB tolerance
        return (
            f"size mismatch (expected {expected:,}, got {actual:,} bytes)"
        )
    return None


def main() -> int:
    print("=" * 50)
    print("  GameAuto - Model File Downloader")
    print("=" * 50)

    missing: list[str] = []
    corrupt: list[str] = []
    ok: list[str] = []

    # Step 1: Check existing files
    print("\n[1/2] Checking existing files ...")
    for name, info in FILES.items():
        issue = check_file(name, info)
        path = info["dir"] / name
        if issue is None:
            size_mb = path.stat().st_size / 1024 / 1024
            print(f"  [OK] {name} ({size_mb:.1f} MB)")
            ok.append(name)
        elif issue == "missing":
            print(f"  [--] {name} - NOT FOUND")
            missing.append(name)
        else:
            print(f"  [!!] {name} - {issue}")
            corrupt.append(name)

    need_download = missing + corrupt
    if not need_download:
        print(f"\n  [OK] All {len(ok)} files ready!")
        return 0

    # Step 2: Download
    print(f"\n[2/2] Downloading {len(need_download)} file(s) ...")
    print(f"  Source: {RELEASE_URL}")

    failed = []
    for name in need_download:
        info = FILES[name]
        url = f"{RELEASE_URL}/{name}"
        dest = info["dir"] / name
        if _download(url, dest, info["desc"]):
            issue = check_file(name, info)
            if issue is None:
                size_mb = dest.stat().st_size / 1024 / 1024
                print(f"  [OK] {name} done ({size_mb:.1f} MB)")
                ok.append(name)
            else:
                print(f"  [!!] {name} verification failed: {issue}")
                failed.append(name)
        else:
            failed.append(name)

    print()
    if failed:
        print(f"  [FAIL] {len(failed)}/{len(need_download)} downloads failed")
        print()
        print("  Please download manually:")
        for name in failed:
            print(f"    {RELEASE_URL}/{name}")
            info = FILES[name]
            print(f"    -> save to {info['dir'] / name}")
        print()
        return 1

    print(f"  [OK] All {len(ok)} files ready!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
