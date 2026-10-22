"""Drawing the hover card (docs/architecture.md §6b): Juice-Mate's own dark look, the settings window's
palette — night navy, one cyan signal for the line, magenta when the item is red on the panel.

Drawn at twice the size and scaled down, so the rounded corners, the chart line and its fill are
smooth. A soft shadow is part of the image: the card is a layered window with per-pixel alpha.
"""

import contextlib
from functools import cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from juice_mate.core.card import Card
from juice_mate.core.display import Tone
from juice_mate.panel.render import _glyph_mask

NIGHT = (10, 10, 25)
SURFACE = (17, 17, 42)
RAISED = (23, 23, 52)
LINE = (35, 35, 74)
LINE_2 = (46, 46, 92)
PAPER = (236, 238, 247)
MIST = (155, 158, 186)
DIM = (108, 111, 143)
SIGNAL = (62, 230, 228)
PULSE = (255, 61, 106)

WIDTH = 300  # at 96 DPI
PAD = 14
SHADOW = 14  # the margin the shadow takes around the card
CHART = 84
SS = 2  # supersampling

Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


@cache
def _font(kind: str, px: int, weight: int = 400) -> Font:
    names = {"text": ("SegUIVar.ttf", "segoeui.ttf"), "mono": ("CascadiaMono.ttf", "CascadiaCode.ttf", "consola.ttf")}[
        kind
    ]
    for name in names:
        try:
            font = ImageFont.truetype(name, px)
        except OSError:
            continue
        if name in ("SegUIVar.ttf", "CascadiaMono.ttf", "CascadiaCode.ttf"):
            with contextlib.suppress(OSError, ValueError):
                axes = font.get_variation_axes()
                rest = [float(a.get("default") or 0) for a in axes[1:]]
                font.set_variation_by_axes([float(weight), *rest])
        return font
    return ImageFont.load_default(px)


def size(card: Card, scale: float) -> tuple[int, int]:
    """The image's size, shadow included."""
    height = PAD + 36 + 10 + 18 * len(card.lines) + 10 + CHART + 18 + PAD
    return round((WIDTH + 2 * SHADOW) * scale), round((height + 2 * SHADOW) * scale)


def draw(card: Card, scale: float = 1.0) -> Image.Image:
    k = scale * SS
    w, h = size(card, scale)
    big = Image.new("RGBA", (w * SS, h * SS), (0, 0, 0, 0))

    def px(v: float) -> int:
        return round(v * k)

    # Shadow, then the card.
    box = (px(SHADOW), px(SHADOW), w * SS - px(SHADOW), h * SS - px(SHADOW))
    shadow = Image.new("L", big.size, 0)
    ImageDraw.Draw(shadow).rounded_rectangle((box[0], box[1] + px(4), box[2], box[3] + px(4)), radius=px(12), fill=150)
    shadow = shadow.filter(ImageFilter.GaussianBlur(px(9)))
    big.paste((0, 0, 0, 255), (0, 0), shadow)
    canvas = ImageDraw.Draw(big)
    canvas.rounded_rectangle(box, radius=px(12), fill=(*SURFACE, 250), outline=(*LINE_2, 255), width=max(1, px(1)))

    x0, y0 = box[0] + px(PAD), box[1] + px(PAD)
    right = box[2] - px(PAD)
    critical = card.tone is Tone.CRITICAL
    accent = PULSE if critical else SIGNAL

    # Header: glyph tile, title, the big number.
    tile = (x0, y0, x0 + px(36), y0 + px(36))
    canvas.rounded_rectangle(tile, radius=px(9), fill=(*RAISED, 255), outline=(*LINE_2, 255), width=max(1, px(1)))
    mask = _glyph_mask(card.glyph, px(18))
    layer = Image.new("RGBA", mask.size, (*accent, 0))
    layer.putalpha(mask)
    big.alpha_composite(layer, (tile[0] + (px(36) - mask.width) // 2, tile[1] + (px(36) - mask.height) // 2))
    value_font = _font("mono", px(20), 600)
    canvas.text(
        (right, y0 + px(18)), card.value, font=value_font, fill=(*(PULSE if critical else PAPER), 255), anchor="rm"
    )
    value_width = canvas.textlength(card.value, font=value_font)
    title_font = _font("text", px(13), 600)
    title = _fit(card.title, title_font, right - value_width - px(12) - (x0 + px(48)))
    canvas.text((x0 + px(48), y0 + px(18)), title, font=title_font, fill=(*PAPER, 255), anchor="lm")

    # The story.
    y = y0 + px(36 + 10)
    body = _font("text", px(12))
    for line in card.lines:
        canvas.text((x0, y + px(9)), _fit(line, body, right - x0), font=body, fill=(*MIST, 255), anchor="lm")
        y += px(18)
    y += px(10)

    # The chart.
    chart = (x0, y, right, y + px(CHART))
    _chart(big, card, chart, accent, k)
    mono = _font("mono", px(10))
    span_h = (card.t1 - card.t0) / 3600
    start = f"−{span_h:.0f}h" if span_h >= 1 else f"−{span_h * 60:.0f}min"
    canvas.text((chart[0], chart[3] + px(12)), start, font=mono, fill=(*DIM, 255), anchor="lm")
    canvas.text((chart[2], chart[3] + px(12)), "now", font=mono, fill=(*DIM, 255), anchor="rm")
    return big.resize((w, h), Image.Resampling.LANCZOS)


def _fit(text: str, font: Font, width: float) -> str:
    probe = ImageDraw.Draw(Image.new("L", (1, 1)))
    if probe.textlength(text, font=font) <= width:
        return text
    while text and probe.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text + "…"


def _chart(
    image: Image.Image, card: Card, box: tuple[int, int, int, int], accent: tuple[int, int, int], k: float
) -> None:
    canvas = ImageDraw.Draw(image)
    left, top, right, bottom = box
    for i in range(3):  # quiet guide lines at 0, half and top
        gy = top + (bottom - top) * i / 2
        canvas.line((left, gy, right, gy), fill=(*LINE, 255), width=max(1, round(k * 0.6)))
    samples = [s for s in card.series if card.t0 <= s.t <= card.t1]
    if len(samples) < 2:
        canvas.text(((left + right) / 2, (top + bottom) / 2), "Collecting history…", font=_font("text", round(12 * k)),
                    fill=(*DIM, 255), anchor="mm")  # fmt: skip
        return
    high = card.y_max or max(s.value for s in samples) * 1.15 or 1.0
    span = max(card.t1 - card.t0, 1.0)

    def at(t: float, v: float) -> tuple[float, float]:
        return left + (right - left) * (t - card.t0) / span, bottom - (bottom - top) * min(max(v / high, 0.0), 1.0)

    if card.charging_marks:  # shade where the battery was on the charger
        runs: list[tuple[float, float]] = []
        for a, b in zip(samples, samples[1:], strict=False):
            if b.charging or a.charging:
                if runs and abs(runs[-1][1] - a.t) < 1:
                    runs[-1] = (runs[-1][0], b.t)
                else:
                    runs.append((a.t, b.t))
        # Translucent shapes go on a layer of their own: drawn straight onto the card they would
        # replace its pixels and punch see-through holes in it.
        shade = Image.new("RGBA", image.size, (0, 0, 0, 0))
        for t0, t1 in runs:
            ImageDraw.Draw(shade).rectangle((at(t0, 0)[0], top, at(t1, 0)[0], bottom), fill=(*SIGNAL, 26))
        image.alpha_composite(shade)

    points = [at(s.t, s.value) for s in samples]
    # The fill: a vertical fade under the line, clipped to the area below it.
    area = Image.new("L", image.size, 0)
    ImageDraw.Draw(area).polygon([(points[0][0], bottom), *points, (points[-1][0], bottom)], fill=255)
    fade = Image.new("L", image.size, 0)
    height = max(bottom - top, 1)
    fade_draw = ImageDraw.Draw(fade)
    for row in range(top, bottom + 1):
        fade_draw.line((left, row, right, row), fill=round(70 * (1 - (row - top) / height)))
    alpha = Image.composite(fade, Image.new("L", image.size, 0), area)
    tint = Image.new("RGBA", image.size, (*accent, 0))
    tint.putalpha(alpha)
    image.alpha_composite(tint)
    canvas.line(points, fill=(*accent, 255), width=max(2, round(2 * k)), joint="curve")
    x, y = points[-1]
    r = 3.2 * k
    halo = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(halo).ellipse((x - 2.2 * r, y - 2.2 * r, x + 2.2 * r, y + 2.2 * r), fill=(*accent, 50))
    image.alpha_composite(halo)
    canvas.ellipse((x - r, y - r, x + r, y + r), fill=(*accent, 255), outline=(*NIGHT, 255), width=max(1, round(k)))
