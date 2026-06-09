"""
Environment checker - verifies everything is ready before first run.
Usage: python check_env.py
"""
import sys
from pathlib import Path


def check_python() -> bool:
    """Check Python version >= 3.10."""
    ver = sys.version_info
    ok = ver >= (3, 10)
    if ok:
        print(f"  [OK] Python {ver.major}.{ver.minor}.{ver.micro}")
    else:
        print(f"  [FAIL] Python {ver.major}.{ver.minor} (need 3.10+)")
    return ok


def check_cuda() -> bool:
    """Check if PyTorch can see the GPU."""
    try:
        import torch
        if torch.cuda.is_available():
            name = torch.cuda.get_device_name(0)
            mem = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
            print(f"  [OK] CUDA ready: {name} ({mem:.1f} GB)")
            return True
        else:
            print("  [WARN] CUDA not available - running on CPU (slow)")
            print("         Install NVIDIA drivers + CUDA Toolkit for GPU speed")
            return True  # not a hard failure
    except ImportError:
        print("  [WARN] PyTorch not installed - run setup.bat first")
        return False


def check_monitors() -> bool:
    """Detect monitors and warn if multi-monitor setup."""
    try:
        import mss
        with mss.mss() as sct:
            monitors = sct.monitors
            active = [m for m in monitors[1:] if m.get("width", 0) > 0]
            if len(active) == 1:
                w, h = active[0]["width"], active[0]["height"]
                print(f"  [OK] Single monitor: {w}x{h}")
                return True
            else:
                print(f"  [WARN] {len(active)} monitors detected:")
                for i, m in enumerate(active):
                    print(f"         Monitor {i+1}: {m['width']}x{m['height']}"
                          f" at ({m['left']},{m['top']})")
                print("         Game MUST be on the primary monitor (Monitor 1)")
                print("         If not, move game window to primary monitor")
                return True  # not a hard failure
    except ImportError:
        print("  [WARN] mss not installed - run setup.bat first")
        return False


def check_files() -> bool:
    """Check required files exist."""
    project = Path(__file__).parent
    required = {
        "models/best_20260601.pt": "YOLO detection model",
        "models/loftr_model.onnx": "LoFTR ONNX model",
        "maps/big_map.png": "Game world map",
        "interception.dll": "Interception driver DLL",
    }
    all_ok = True
    for path, desc in required.items():
        full = project / path
        if full.exists():
            size_mb = full.stat().st_size / 1024 / 1024
            print(f"  [OK] {path} ({size_mb:.1f} MB)")
        else:
            print(f"  [MISS] {path} - {desc}")
            all_ok = False
    if not all_ok:
        print("         Run: python download_models.py")
    return all_ok


def pre_warm_loftr() -> bool:
    """Pre-download LoFTR model weights so first run doesn't stall.

    Kornia LoFTR downloads ~40MB of weights from torch hub on first use.
    This pre-warms the cache so the user doesn't see a silent hang.
    """
    print("  Downloading LoFTR model weights (~40 MB, one-time only) ...")
    try:
        import torch
        # Suppress kornia deprecation warnings during download
        import warnings
        warnings.filterwarnings("ignore")

        # Force download now (same code as hybrid_positioner.py)
        from kornia.feature import LoFTR
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        model = LoFTR(pretrained='outdoor').to(device)
        model.eval()

        # Quick smoke test to verify the model works
        h, w = 256, 256  # must be divisible by 8
        dummy0 = torch.rand(1, 1, h, w, device=device)
        dummy1 = torch.rand(1, 1, h, w, device=device)
        with torch.no_grad():
            if device.type == 'cuda':
                with torch.autocast(device_type='cuda', dtype=torch.float16):
                    out = model({"image0": dummy0, "image1": dummy1})
            else:
                out = model({"image0": dummy0, "image1": dummy1})
        print("  [OK] LoFTR model ready and verified")
        return True
    except Exception as e:
        msg = str(e).lower()
        if "timeout" in msg or "ssl" in msg or "connection" in msg:
            print(f"  [FAIL] Network error downloading LoFTR model")
            print(f"         Check your internet connection and VPN")
            print(f"         The navigation will fail until this model is cached")
        elif "out of memory" in msg or "oom" in msg:
            print(f"  [FAIL] GPU out of memory - need 2GB+ VRAM available")
            print(f"         Close other GPU-heavy applications and retry")
        else:
            print(f"  [FAIL] LoFTR model failed: {e}")
            print(f"         Navigation will not work. Re-run setup.bat or check_env.py")
        return False


def main() -> int:
    print("=" * 50)
    print("  GameAuto - Environment Check")
    print("=" * 50)

    results = {
        "Python": check_python(),
        "CUDA/GPU": check_cuda(),
        "Monitors": check_monitors(),
        "Files": check_files(),
    }

    print()
    all_basic = all(results.values())
    if not all_basic:
        print("[FAIL] Some checks failed - fix above issues before running")
        print()
        return 1

    print("[1/1] Pre-warming AI models (one-time setup) ...")
    print()
    loftr_ok = pre_warm_loftr()

    print()
    if loftr_ok:
        print("=" * 50)
        print("  All checks passed! Ready to run.")
        print("=" * 50)
        print()
        print("  Next: double-click run.bat")
        return 0
    else:
        print("[FAIL] LoFTR model download failed")
        print("  Fix the network issue and re-run: python check_env.py")
        return 1


if __name__ == "__main__":
    sys.exit(main())
