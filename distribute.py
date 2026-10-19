"""Simple distribution helper for Ever Recover."""

from pathlib import Path
import shutil
import subprocess
import sys


def main() -> int:
    project_root = Path(__file__).resolve().parent
    dist_dir = project_root / "dist"
    build_dir = project_root / "build"

    if dist_dir.exists():
        shutil.rmtree(dist_dir)
    if build_dir.exists():
        shutil.rmtree(build_dir)

    subprocess.run([sys.executable, "-m", "pip", "install", "--upgrade", "build"], check=True)
    subprocess.run([sys.executable, "-m", "build"], check=True)

    print(f"Distribution artifacts created in {dist_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
