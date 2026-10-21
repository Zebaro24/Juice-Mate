"""Draw the panel items in the system's style: a glyph and a number, no boxes (docs/architecture.md §6).

Two rows, filled column by column, the way TrafficMonitor lays out its numbers. Returns the image and
each item's rectangle, so the window knows which item the mouse is over.
"""

import contextlib
from dataclasses import dataclass
from functools import cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from juice_mate.core.display import BOLT, Item, Tone

_ICON_FONTS = ("SegoeIcons.ttf", "segmdl2.ttf")  # Windows 11, Windows 10
_TEXT_FONTS = ("SegUIVar.ttf", "segoeui.ttf")
_SYMBOL_FONTS = ("seguisym.ttf",)  # glyphs outside the icon fonts, e.g. Claude's spark
_PRIVATE_USE = range(0xE000, 0xF900)  # where the icon fonts keep their glyphs

# Sizes at 96 DPI, for two rows in a 48 px taskbar.
GLYPH_PX = 14
TEXT_PX = 12
TAG_PX = 9
BOLT_PX = 9


@dataclass(frozen=True)
class Theme:
    text: tuple[int, int, int]
    critical: tuple[int, int, int]
    dim_alpha: int

    @staticmethod
    def for_taskbar(light: bool) -> "Theme":
        # Fluent's text and "critical" colours for each taskbar theme.
        if light:
            return Theme(text=(0, 0, 0), critical=(196, 43, 28), dim_alpha=150)
        return Theme(text=(255, 255, 255), critical=(255, 153, 164), dim_alpha=150)


@dataclass(frozen=True)
class Span:
    key: str
    left: int
    top: int
    right: int
    bottom: int
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


_SUPERSAMPLE = 4
_DILATE = 3  # a 3×3 max filter at 4×: each stroke grows by about a quarter pixel per side


@cache
def _glyph_mask(glyph: str, size: int) -> Image.Image:
    """The glyph's coverage, a little bolder than FreeType draws it.

    Segoe Fluent Icons at tray size comes out hairline-thin next to the taskbar's own Wi-Fi and
    volume glyphs. Drawing at 4×, growing every stroke, and scaling down matches their weight
    without smearing the detail (a keyboard's keys stay apart).
    """
    names = _ICON_FONTS if ord(glyph[0]) in _PRIVATE_USE else _SYMBOL_FONTS
    big = _font(names, size * _SUPERSAMPLE)
    left, top, right, bottom = big.getbbox(glyph)
    pad = 2 * _SUPERSAMPLE
    width = int(right - left + 0.999) + 2 * pad
    height = size * _SUPERSAMPLE + 2 * pad
    width += -width % _SUPERSAMPLE
    height += -height % _SUPERSAMPLE
    mask = Image.new("L", (width, height), 0)
    y = pad + (size * _SUPERSAMPLE - (bottom - top)) / 2 - top
    ImageDraw.Draw(mask).text((pad - left, y), glyph, font=big, fill=255)
    mask = mask.filter(ImageFilter.MaxFilter(_DILATE))
    return mask.resize((width // _SUPERSAMPLE, height // _SUPERSAMPLE), Image.Resampling.LANCZOS)


def _paste_glyph(image: Image.Image, glyph: str, size: int, x: float, mid: float, fill: tuple[int, ...]) -> int:
    """Draw the glyph with its left edge at `x`, centred on `mid`; returns its drawn width."""
    mask = _glyph_mask(glyph, size)
    pad = 2  # the mask's padding at 1×
    layer = Image.new("RGBA", mask.size, fill[:3] + (0,))
    layer.putalpha(mask.point([v * fill[3] // 255 for v in range(256)]))
    image.alpha_composite(layer, (round(x) - pad, round(mid - mask.height / 2)))
    return mask.width - 2 * pad


# Alpha 1 everywhere: a fully transparent pixel of a layered window lets clicks through to the taskbar.
_BACKGROUND = (0, 0, 0, 1)


def render(items: list[Item], height: int, theme: Theme, scale: float = 1.0) -> tuple[Image.Image, list[Span]]:
    """Items in two rows, filled column by column. `scale` is the DPI scale (1.0 at 96 DPI)."""
    glyph_px, bolt_px = round(GLYPH_PX * scale), round(BOLT_PX * scale)
    text_font = _font(_TEXT_FONTS, round(TEXT_PX * scale))
    tag_font = _font(_TEXT_FONTS, round(TAG_PX * scale))
    gap_inner, gap_column, pad = round(4 * scale), round(12 * scale), round(6 * scale)

    def width_of(it: Item) -> int:
        w = _glyph_mask(it.glyph, glyph_px).width - 4
        if it.charging:
            w += gap_inner + _glyph_mask(BOLT, bolt_px).width - 4
        if it.tag:
            w += gap_inner + _width(tag_font, it.tag)
        if it.text:
            w += gap_inner + _width(text_font, it.text)
        return w

    columns = [items[i : i + 2] for i in range(0, len(items), 2)]
    widths = [max(width_of(it) for it in column) for column in columns]
    total = pad * 2 + sum(widths) + gap_column * max(len(columns) - 1, 0)

    image = Image.new("RGBA", (max(total, 1), height), _BACKGROUND)
    canvas = ImageDraw.Draw(image)
    rows = (height * 0.29, height * 0.71)
    spans = []
    x = pad
    for column, column_width in zip(columns, widths, strict=True):
        # A column with one item sits in the middle, not in the top row.
        centres = [height / 2] if len(column) == 1 else list(rows)
        for it, mid in zip(column, centres, strict=False):
            colour = theme.critical if it.tone is Tone.CRITICAL else theme.text
            fill = (*colour, theme.dim_alpha if it.tone is Tone.DIM else 255)
            cursor = x + _paste_glyph(image, it.glyph, glyph_px, x, mid, fill)
            if it.badge:
                _paste_glyph(image, it.badge, bolt_px, cursor - bolt_px / 2, mid + glyph_px / 3, fill)
            if it.charging:
                cursor += gap_inner
                cursor += _paste_glyph(image, BOLT, bolt_px, cursor, mid, fill)
            if it.tag:
                cursor += gap_inner
                canvas.text((cursor, mid), it.tag, font=tag_font, fill=(*colour, theme.dim_alpha), anchor="lm")
                cursor += _width(tag_font, it.tag)
            if it.text:
                cursor += gap_inner
                canvas.text((cursor, mid), it.text, font=text_font, fill=fill, anchor="lm")
            # Hover areas split the column at the middle: top item above, bottom item below.
            top, bottom = (
                (0, height) if len(column) == 1 else (0, height // 2) if mid < height / 2 else (height // 2, height)
            )
            spans.append(Span(it.key, x, top, x + column_width, bottom, it.tooltip))
        x += column_width + gap_column
    return _thicken_text(image), spans


# Windows draws text with gamma-corrected antialiasing; FreeType's linear coverage looks thinner next
# to the clock. Lifting the edge alpha along this curve matches it. Glyphs are already bold enough.
_GAMMA = 0.6
_ALPHA_CURVE = [v if v <= 1 else round(255 * (v / 255) ** _GAMMA) for v in range(256)]


def _thicken_text(image: Image.Image) -> Image.Image:
    image.putalpha(image.getchannel("A").point(_ALPHA_CURVE))
    return image


def premultiplied_bgra(image: Image.Image) -> bytes:
    """The pixel format UpdateLayeredWindow wants: premultiplied alpha, BGRA byte order."""
    return image.convert("RGBa").tobytes("raw", "BGRa")
