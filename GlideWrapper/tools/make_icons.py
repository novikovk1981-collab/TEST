"""Генерация иконок лаунчера (PNG) для проекта VzletKB.

Рисует «бумажный самолёт» на фирменном синем фоне и раскладывает
по всем плотностям mipmap-*. Legacy-PNG нужны для API 26 (адаптивные —
в mipmap-anydpi-v26/ic_launcher.xml).
"""

from PIL import Image, ImageDraw
import os
import sys

BLUE = (13, 71, 161, 255)
SEND_PATH = [(2.01, 21), (23, 12), (2.01, 3), (2, 10), (17, 12), (2, 14)]

DENSITIES = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}


def render(size: int, round_icon: bool = False, supersample: int = 8) -> Image.Image:
    s = size * supersample
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    radius = s // 2 if round_icon else int(s * 0.22)
    draw.rounded_rectangle([0, 0, s - 1, s - 1], radius=radius, fill=BLUE)

    scale = (s * 0.60) / 24.0
    ox = (s - 24 * scale) / 2.0
    oy = (s - 24 * scale) / 2.0 - s * 0.02
    pts = [(ox + x * scale, oy + y * scale) for x, y in SEND_PATH]
    draw.polygon(pts, fill=(255, 255, 255, 255))

    return img.resize((size, size), Image.LANCZOS)


def main(res_dir: str) -> None:
    for density, size in DENSITIES.items():
        out = os.path.join(res_dir, f"mipmap-{density}")
        os.makedirs(out, exist_ok=True)
        render(size).save(os.path.join(out, "ic_launcher.png"))
        render(size, round_icon=True).save(os.path.join(out, "ic_launcher_round.png"))
        print(f"mipmap-{density}: {size}x{size}")

    # исходник для стора / превью (res -> main -> src -> app -> корень проекта)
    root = os.path.abspath(os.path.join(res_dir, "..", "..", "..", ".."))
    render(512).save(os.path.join(root, "icon-512.png"))
    render(512, round_icon=True).save(os.path.join(root, "icon-512-round.png"))
    print("icon-512.png, icon-512-round.png")


if __name__ == "__main__":
    res = sys.argv[1] if len(sys.argv) > 1 else "app/src/main/res"
    main(res)
