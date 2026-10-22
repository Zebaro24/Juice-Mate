#!/usr/bin/env python3
"""Draw the Juice-Mate logo: an upright battery filled with juice, a mate leaf on its cap.

    poetry run python scripts/logo.py            # writes docs/logo.png (the README's)
    scripts/build.py calls icon() for the exe's .ico

Drawn in code, not kept as artwork: one source for every size. Drawn at 4× and scaled down.
"""

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
S = 4  # supersampling
BASE = 256  # design grid

BG_TOP, BG_BOTTOM = (28, 33, 52), (12, 15, 26)  # night navy
JUICE_TOP, JUICE_BOTTOM = (255, 214, 64), (255, 128, 31)  # citrus
LEAF, LEAF_VEIN = (88, 201, 112), (40, 140, 70)
SHELL = (236, 240, 248)


def _gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    column = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / max(size - 1, 1)
        column.putpixel((0, y), tuple(round(a + (b - a) * t) for a, b in zip(top, bottom, strict=True)))
    return column.resize((size, size))


def draw(size: int = 1024) -> Image.Image:
    big = size * S
    k = big / BASE  # design units → pixels

    def box(x0: float, y0: float, x1: float, y1: float) -> tuple[float, float, float, float]:
        return (x0 * k, y0 * k, x1 * k, y1 * k)

    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))

    # Background squircle with a soft vertical gradient.
    mask = Image.new("L", (big, big), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box(8, 8, 248, 248), radius=56 * k, fill=255)
    image.paste(_gradient(big, BG_TOP, BG_BOTTOM), (0, 0), mask)

    # Glow behind the battery.
    glow = Image.new("L", (big, big), 0)
    ImageDraw.Draw(glow).ellipse(box(58, 70, 198, 230), fill=70)
    glow = glow.filter(ImageFilter.GaussianBlur(28 * k))
    image.paste((255, 170, 50), (0, 0), Image.composite(glow, Image.new("L", (big, big), 0), mask))

    canvas = ImageDraw.Draw(image)
    # Battery shell and cap.
    shell = box(84, 62, 172, 222)
    canvas.rounded_rectangle(box(110, 46, 146, 66), radius=6 * k, fill=SHELL)
    canvas.rounded_rectangle(shell, radius=22 * k, fill=SHELL)
    inner = box(96, 74, 160, 210)
    canvas.rounded_rectangle(inner, radius=13 * k, fill=BG_BOTTOM)

    # Juice: gradient clipped to the inside, with a wave on top at ~70 %.
    juice_mask = Image.new("L", (big, big), 0)
    jm = ImageDraw.Draw(juice_mask)
    jm.rounded_rectangle(inner, radius=13 * k, fill=255)
    level = 112  # design y of the surface
    wave = Image.new("L", (big, big), 0)
    points = [(96 * k, 230 * k)]
    for i in range(0, 65):
        x = 96 + i
        points.append((x * k, (level + 4.5 * math.sin((x - 96) / 64 * 2 * math.pi * 1.25)) * k))
    points.append((160 * k, 230 * k))
    ImageDraw.Draw(wave).polygon(points, fill=255)
    juice_mask = Image.composite(juice_mask, Image.new("L", (big, big), 0), wave)
    image.paste(_gradient(big, JUICE_TOP, JUICE_BOTTOM), (0, 0), juice_mask)

    # Bubbles and a highlight on the shell.
    for cx, cy, r in ((116, 176, 6), (138, 150, 4), (124, 136, 3)):
        canvas.ellipse(box(cx - r, cy - r, cx + r, cy + r), fill=(255, 240, 190, 200))
    canvas.rounded_rectangle(box(102, 82, 108, 104), radius=3 * k, fill=(255, 255, 255, 60))

    # Mate leaf leaning off the cap.
    leaf = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ld = ImageDraw.Draw(leaf)
    ld.ellipse(box(146, 20, 206, 48), fill=LEAF)
    ld.line([(150 * k, 36 * k), (202 * k, 32 * k)], fill=LEAF_VEIN, width=round(3 * k))
    ld.line([(140 * k, 50 * k), (152 * k, 36 * k)], fill=LEAF, width=round(5 * k))  # stem to the cap
    leaf = leaf.rotate(-28, center=(146 * k, 44 * k), resample=Image.Resampling.BICUBIC)
    image.alpha_composite(leaf)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def icon(path: Path) -> None:
    """The exe's .ico: every size from 16 to 256 px."""
    path.parent.mkdir(parents=True, exist_ok=True)
    draw(256).save(path, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main() -> int:
    out = ROOT / "docs" / "logo.png"
    draw(512).save(out)
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
