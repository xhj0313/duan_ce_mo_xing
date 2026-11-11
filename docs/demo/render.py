"""用 Edge 无头模式把 docs/demo/*.html 渲染成 2 倍 PNG。

用法：python render.py            # 渲染全部屏幕
     python render.py 03-chat-bill  # 只渲染指定屏
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
W, H, SCALE = 390, 844, 2


def render(stem: str) -> Path:
    src = HERE / f"{stem}.html"
    dst = HERE / f"{stem}.png"
    url = "file:///" + str(src).replace("\\", "/")
    subprocess.run([
        EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars",
        f"--force-device-scale-factor={SCALE}", f"--window-size={W},{H}",
        f"--screenshot={dst}", url,
    ], check=True, capture_output=True)
    return dst


def main() -> None:
    targets = sys.argv[1:] or sorted(p.stem for p in HERE.glob("*.html") if p.stem != "index")
    for stem in targets:
        out = render(stem)
        print(f"{out.name}  {out.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()
