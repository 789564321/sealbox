"""生成应用图标（ICO + PNG），供 PyInstaller 与窗口使用。"""

from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packaging"


def build(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    margin = max(2, int(size * 0.03))
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=int(size * 0.24),
        fill=(37, 99, 235, 255),
    )
    pad = size * 0.22
    draw.arc(
        [size * 0.30, size * 0.20, size * 0.70, size * 0.60],
        start=180,
        end=360,
        fill=(255, 255, 255, 255),
        width=max(3, int(size * 0.075)),
    )
    draw.rounded_rectangle(
        [size * 0.27, size * 0.42, size * 0.73, size * 0.78],
        radius=int(size * 0.08),
        fill=(255, 255, 255, 255),
    )
    draw.ellipse(
        [size * 0.45, size * 0.53, size * 0.55, size * 0.63],
        fill=(37, 99, 235, 255),
    )
    draw.rounded_rectangle(
        [size * 0.48, size * 0.60, size * 0.52, size * 0.70],
        radius=max(1, int(size * 0.015)),
        fill=(37, 99, 235, 255),
    )
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    base = build(256)
    base.save(OUT / "sealbox-256.png")
    base.save(
        OUT / "sealbox.ico",
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    print(f"icon: {OUT / 'sealbox.ico'}")


if __name__ == "__main__":
    main()
