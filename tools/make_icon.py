"""Generate assets/icon.ico (a document with a Markdown "M↓" mark) using Pillow.

Usage: python tools/make_icon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

SIZE = 256
OUT = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"


def draw(size: int = SIZE) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256

    # Rounded blue tile
    d.rounded_rectangle((8 * s, 8 * s, 248 * s, 248 * s), radius=48 * s, fill=(31, 106, 165))

    # White "M" built from strokes
    w = 22 * s
    left, right, top, bottom = 44 * s, 140 * s, 70 * s, 186 * s
    mid = (left + right) / 2
    d.line([(left, bottom), (left, top), (mid, top + 62 * s), (right, top), (right, bottom)],
           fill="white", width=int(w), joint="curve")

    # Down arrow
    ax = 188 * s
    d.line([(ax, top), (ax, bottom - 30 * s)], fill="white", width=int(w))
    d.polygon([(ax - 34 * s, bottom - 44 * s), (ax + 34 * s, bottom - 44 * s), (ax, bottom + 4 * s)], fill="white")
    return img


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    draw().save(OUT, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print(f"Wrote {OUT}")
