"""Draw the panel items in the system's style: a glyph and a number, no boxes (docs/architecture.md §6).

Returns the image and each item's horizontal span, so the window knows which item the mouse is over.
"""

import contextlib
from dataclasses import dataclass
from functools import cache

from PIL import Image, ImageDraw, ImageFont

from juice_mate.core.display import BOLT, Item, Tone

_ICON_FONTS = ("SegoeIcons.ttf", "segmdl2.ttf")  # Windows 11, Windows 10
_TEXT_FONTS = ("SegUIVar.ttf", "segoeui.ttf")
_SYMBOL_FONTS = ("seguisym.ttf",)  # glyphs outside the icon fonts, e.g. Claude's spark


@dataclass(frozen=True)
class Theme:
    text: tuple[int, int, int]
    critical: tuple[int, int, int]
    dim_alpha: int

    @staticmethod
    def for_taskbar(light: bool) -> "Theme":
        # Fluent's text and "critical" colours for each taskbar theme.
        if light:
            return Theme(text=(0, 0, 0), critical=(196, 43, 28), dim_alpha=170)
        return Theme(text=(255, 255, 255), critical=(255, 153, 164), dim_alpha=170)


@dataclass(frozen=True)
class Span:
    key: str
    left: int
    right: int
    tooltip: str


Font = ImageFont.FreeTypeFont | ImageFont.ImageFont


@cache
def _font(names: tuple[str, ...], size: int) -> Font:
    for name in names:
        try:
            font = ImageFont.truetype(name, size)
        except OSError:
            continue
        if name == "SegUIVar.ttf":
            with contextlib.suppress(OSError, ValueError):
                font.set_variation_by_name("Regular")
        return font
    return ImageFont.load_default(size)


def _width(font: Font, text: str) -> int:
    if not text:
        return 0
    left, _top, right, _bottom = font.getbbox(text)
    return int(right - left + 0.999)


# Alpha 1 everywhere: a fully transparent pixel of a layered window lets clicks through to the taskbar.
_BACKGROUND = (0, 0, 0, 1)


def render(items: list[Item], height: int, theme: Theme, scale: float = 1.0) -> tuple[Image.Image, list[Span]]:
    """One row of items, vertically centred in `height` pixels. `scale` is the DPI scale (1.0 at 96 DPI)."""
    # Sizes of the taskbar's own glyphs and clock at 96 DPI.
    glyph_font = _font(_ICON_FONTS, round(16 * scale))
    small_glyph = _font(_ICON_FONTS, round(10 * scale))
    text_font = _font(_TEXT_FONTS, round(14 * scale))
    gap_inner, gap_outer, pad = round(5 * scale), round(14 * scale), round(6 * scale)

    symbol_font = _font(_SYMBOL_FONTS, round(16 * scale))

    def glyph_font_for(glyph: str) -> Font:
        # The icon fonts live in the Private Use Area; anything else comes from Segoe UI Symbol.
        return glyph_font if "\ue000" <= glyph <= "\uf8ff" else symbol_font

    widths = []
    for it in items:
        w = _width(glyph_font_for(it.glyph), it.glyph)
        if it.charging:
            w += gap_inner + _width(small_glyph, BOLT)
        if it.text:
            w += gap_inner + _width(text_font, it.text)
        widths.append(w)
    total = pad * 2 + sum(widths) + gap_outer * max(len(items) - 1, 0)

    image = Image.new("RGBA", (max(total, 1), height), _BACKGROUND)
    canvas = ImageDraw.Draw(image)
    mid = height / 2
    x = pad
    spans = []
    for it, w in zip(items, widths, strict=True):
        start = x
        colour = theme.critical if it.tone is Tone.CRITICAL else theme.text
        alpha = theme.dim_alpha if it.tone is Tone.DIM else 255
        fill = (*colour, alpha)
        font = glyph_font_for(it.glyph)
        canvas.text((x, mid), it.glyph, font=font, fill=fill, anchor="lm")
        glyph_w = _width(font, it.glyph)
        if it.struck:
            # A diagonal stroke over the glyph, the way Windows crosses out a muted speaker.
            half = glyph_w / 2 + scale
            cx = x + glyph_w / 2
            canvas.line(
                [(cx - half, mid + half), (cx + half, mid - half)], fill=(*theme.text, 230), width=round(1.6 * scale)
            )
        if it.badge:
            canvas.text((x + glyph_w, mid + glyph_w / 2), it.badge, font=small_glyph, fill=fill, anchor="mm")
        x += glyph_w
        if it.charging:
            x += gap_inner
            canvas.text((x, mid), BOLT, font=small_glyph, fill=fill, anchor="lm")
            x += _width(small_glyph, BOLT)
        if it.text:
            x += gap_inner
            canvas.text((x, mid), it.text, font=text_font, fill=fill, anchor="lm")
            x += _width(text_font, it.text)
        spans.append(Span(it.key, start, x, it.tooltip))
        x = start + w + gap_outer
    return _thicken(image), spans


# Windows draws its glyphs with gamma-corrected antialiasing; FreeType's linear coverage looks thinner
# next to them. Lifting the edge alpha along this curve matches the taskbar's own Wi-Fi / volume glyphs.
_GAMMA = 0.45
_ALPHA_CURVE = [v if v <= 1 else round(255 * (v / 255) ** _GAMMA) for v in range(256)]


def _thicken(image: Image.Image) -> Image.Image:
    image.putalpha(image.getchannel("A").point(_ALPHA_CURVE))
    return image


def premultiplied_bgra(image: Image.Image) -> bytes:
    """The pixel format UpdateLayeredWindow wants: premultiplied alpha, BGRA byte order."""
    return image.convert("RGBa").tobytes("raw", "BGRa")
