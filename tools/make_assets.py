"""Generate the app icon and installer artwork with Pillow.

Outputs (committed to the repo, so builds do not need to run this):
    assets/icon.ico                     app / installer icon, 16-256 px
    assets/installer/wizard-*.png       Inno Setup side panel, one per DPI scale
    assets/installer/small-*.png        Inno Setup header logo, one per DPI scale

Usage: python tools/make_assets.py
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
BLUE = (31, 106, 165)
DEEP_BLUE = (14, 52, 92)

# Inno Setup picks the best match for the user's DPI from these sizes.
DPI_SCALES = (100, 125, 150, 175, 200, 250)
WIZARD_SIZE = (164, 314)      # left panel on the Welcome / Finished pages at 100 %
SMALL_SIZE = (58, 58)         # top-right logo on inner pages at 100 %


def draw_glyph(d: ImageDraw.ImageDraw, x0: float, y0: float, s: float, fill="white") -> None:
    """Draw the "M↓" Markdown mark into a 256*s square whose top-left is (x0, y0)."""
    w = int(22 * s)
    left, right, top, bottom = x0 + 44 * s, x0 + 140 * s, y0 + 70 * s, y0 + 186 * s
    mid = (left + right) / 2
    d.line([(left, bottom), (left, top), (mid, top + 62 * s), (right, top), (right, bottom)],
           fill=fill, width=w, joint="curve")
    ax = x0 + 188 * s
    d.line([(ax, top), (ax, bottom - 30 * s)], fill=fill, width=w)
    d.polygon([(ax - 34 * s, bottom - 44 * s), (ax + 34 * s, bottom - 44 * s), (ax, bottom + 4 * s)], fill=fill)


def draw_icon(size: int = 256) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256
    d.rounded_rectangle((8 * s, 8 * s, 248 * s, 248 * s), radius=48 * s, fill=BLUE)
    draw_glyph(d, 0, 0, s)
    return img


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_wizard_panel(width: int, height: int) -> Image.Image:
    """Vertical brand gradient with the logo and app name."""
    img = Image.new("RGB", (width, height))
    d = ImageDraw.Draw(img)
    for y in range(height):
        t = y / max(height - 1, 1)
        d.line([(0, y), (width, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BLUE, DEEP_BLUE)))

    scale = width / WIZARD_SIZE[0]
    logo = int(110 * scale)
    draw_glyph(d, (width - logo) / 2, height * 0.22, logo / 256)

    font = _font(int(19 * scale))
    text = "mdConverter"
    tw = d.textlength(text, font=font)
    d.text(((width - tw) / 2, height * 0.22 + logo + 6 * scale), text, font=font, fill="white")

    sub = _font(int(10 * scale))
    tag = "Documents to Markdown"
    sw = d.textlength(tag, font=sub)
    d.text(((width - sw) / 2, height * 0.22 + logo + 32 * scale), tag, font=sub, fill=(200, 220, 240))
    return img


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    draw_icon().save(ASSETS / "icon.ico", sizes=[(n, n) for n in (16, 20, 24, 32, 40, 48, 64, 128, 256)])

    out = ASSETS / "installer"
    out.mkdir(exist_ok=True)
    for pct in DPI_SCALES:
        w, h = (round(v * pct / 100) for v in WIZARD_SIZE)
        draw_wizard_panel(w, h).save(out / f"wizard-{pct}.png")
        sw, _ = (round(v * pct / 100) for v in SMALL_SIZE)
        draw_icon(sw).save(out / f"small-{pct}.png")
    print(f"Wrote icon and installer images to {ASSETS}")


if __name__ == "__main__":
    main()
