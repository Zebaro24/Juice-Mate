"""Draw the panel items in the system's style: a glyph and a number, no boxes (docs/architecture.md §6).

Two rows, filled column by column, the way TrafficMonitor lays out its numbers. Returns the image and
each item's rectangle, so the window knows which item the mouse is over.
"""

import contextlib
from dataclasses import dataclass
from functools import cache
from itertools import groupby

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from juice_mate.core.display import BOLT, Item, Tone

_ICON_FONTS = ("SegoeIcons.ttf", "segmdl2.ttf")  # Windows 11, Windows 10
_TEXT_FONTS = ("SegUIVar.ttf", "segoeui.ttf")
_SYMBOL_FONTS = ("seguisym.ttf",)  # glyphs outside the icon fonts, e.g. Claude's spark
_PRIVATE_USE = range(0xE000, 0xF900)  # where the icon fonts keep their glyphs

# At 96 DPI, for two rows in a 48 px taskbar. Measured on the owner's screen, 2026-10-22: the clock's
# digits are 9 px tall, its rows centred at y 15 and 31. Measured-equal 13 px (9 px digits) still read
# smaller than the clock to the owner, 12 px "tiny": 14 px, 10 px digits. The rows sit 2 px further
# apart than the clock's (owner).
GLYPH_PX = 16
TEXT_PX = 14
TEXT_WEIGHT = 600  # Semibold: at 450 the strokes still read thinner than the clock's (owner, 2026-10-22)
BOLT_PX = 10
ROWS = (14 / 48, 32 / 48)  # row centres as a share of the taskbar height
GAP_INNER = 5  # glyph to number
GAP_COLUMN = 12  # between columns of one group
GAP_GROUP = 18  # between the usage column and the devices: spacing is the separator
PAD = 8
TAG_ALPHA = 190  # "5h" / "7d": the size of the number (owner), a step quieter


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
                font.set_variation_by_axes([TEXT_WEIGHT, max(5.0, min(size * 0.75, 36.0))])  # weight, opsz
        return font
    return ImageFont.load_default(size)


def _width(font: Font, text: str) -> int:
    if not text:
        return 0
    left, _top, right, _bottom = font.getbbox(text)
    return int(right - left + 0.999)


_SUPERSAMPLE = 4
_DILATE = 3  # a 3×3 max filter at 4×: each stroke grows by about a quarter pixel per side
_DILATE_SYMBOL = 5  # Segoe UI Symbol's spokes are thinner still: half a pixel per side


@cache
def _glyph_mask(glyph: str, size: int) -> Image.Image:
    """The glyph's coverage, a little bolder than FreeType draws it.

    Segoe Fluent Icons at tray size comes out hairline-thin next to the taskbar's own Wi-Fi and
    volume glyphs. Drawing at 4×, growing every stroke, and scaling down matches their weight
    without smearing the detail (a keyboard's keys stay apart).
    """
    icon = ord(glyph[0]) in _PRIVATE_USE
    names = _ICON_FONTS if icon else _SYMBOL_FONTS
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
    mask = mask.filter(ImageFilter.MaxFilter(_DILATE if icon else _DILATE_SYMBOL))
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
    """Items in two rows, filled column by column. `scale` is the DPI scale (1.0 at 96 DPI).

    Inside a column every item has the same slots — glyph, then a tag or a bolt, then the number
    right-aligned in a slot at least as wide as "00%" — so 9% → 10% or 88% → 89% moves nothing and
    the % signs line up; only a 100% widens its column. A suffix (`→16:00`) follows the number in
    its own slot, as quiet as a tag.
    """
    glyph_px, bolt_px = round(GLYPH_PX * scale), round(BOLT_PX * scale)
    text_font = _font(_TEXT_FONTS, round(TEXT_PX * scale))
    gap_inner, pad = round(GAP_INNER * scale), round(PAD * scale)
    # The baseline that centres a digit's ink on the row (digits have no descenders).
    _left, digit_top, _right, digit_bottom = text_font.getbbox("0", anchor="ls")
    to_baseline = round((digit_bottom - digit_top) / 2)  # whole pixels: a half-pixel baseline blurs every stroke

    def glyph_size(it: Item) -> int:
        return round(glyph_px * it.glyph_scale)

    def glyph_width(it: Item) -> int:
        return _glyph_mask(it.glyph, glyph_size(it)).width - 4

    def prefix_width(it: Item) -> int:
        if it.tag:
            return _width(text_font, it.tag) + gap_inner
        if it.charging:
            return _glyph_mask(BOLT, bolt_px).width - 4 + gap_inner
        return 0

    # Columns are cut inside each group: an odd number of devices must not push ↓ away from ↑.
    columns = [
        group_items[i : i + 2]
        for _group, members in groupby(items, key=lambda it: it.group)
        for group_items in [list(members)]
        for i in range(0, len(group_items), 2)
    ]
    layout = []
    for column in columns:
        glyph_slot = max(glyph_width(it) for it in column)
        prefix_slot = max(prefix_width(it) for it in column)
        slot = max([_width(text_font, it.reserve) for it in column] + [_width(text_font, it.text) for it in column])
        suffix_slot = max((_width(text_font, it.suffix) + gap_inner if it.suffix else 0) for it in column)
        layout.append(
            (column, glyph_slot, prefix_slot, slot, glyph_slot + gap_inner + prefix_slot + slot + suffix_slot)
        )
    gaps = [
        round((GAP_GROUP if left[0][-1].group != right[0][0].group else GAP_COLUMN) * scale)
        for left, right in zip(layout, layout[1:], strict=False)
    ]
    total = pad * 2 + sum(entry[4] for entry in layout) + sum(gaps)

    image = Image.new("RGBA", (max(total, 1), height), _BACKGROUND)
    canvas = ImageDraw.Draw(image)
    rows = [height * share for share in ROWS]
    spans = []
    x = pad
    for index, (column, glyph_slot, prefix_slot, slot, width) in enumerate(layout):
        # A lone item stays in the top row: centred, it would line up with neither row of the clock.
        for row, (it, mid) in enumerate(zip(column, rows, strict=False)):
            colour = theme.critical if it.tone is Tone.CRITICAL else theme.text
            fill = (*colour, theme.dim_alpha if it.tone is Tone.DIM else 255)
            _paste_glyph(image, it.glyph, glyph_size(it), x + (glyph_slot - glyph_width(it)) / 2, mid, fill)
            cursor = x + glyph_slot + gap_inner
            if it.tag:
                tag_fill = (*colour, min(fill[3], TAG_ALPHA))
                canvas.text(
                    (round(cursor), round(mid) + to_baseline), it.tag, font=text_font, fill=tag_fill, anchor="ls"
                )
            elif it.charging:
                _paste_glyph(image, BOLT, bolt_px, cursor, mid, fill)
            right = cursor + prefix_slot + slot
            if it.text:
                canvas.text((round(right), round(mid) + to_baseline), it.text, font=text_font, fill=fill, anchor="rs")
            if it.suffix:
                quiet = (*colour, min(fill[3], TAG_ALPHA))
                at = (round(right + gap_inner), round(mid) + to_baseline)
                canvas.text(at, it.suffix, font=text_font, fill=quiet, anchor="ls")
            # Hover areas split the column at the middle: top item above, bottom item below.
            top, bottom = (0, height // 2) if row == 0 else (height // 2, height)
            if len(column) == 1:
                top, bottom = 0, height
            spans.append(Span(it.key, x, top, x + width, bottom, it.tooltip))
        x += width + (gaps[index] if index < len(gaps) else 0)
    return _thicken_text(image), spans


# Windows draws the clock with contrast-enhanced antialiasing: solid stems, thin edges. FreeType's
# linear coverage spreads a stem over two grey pixels and reads blurry beside it ("the clock is
# crisper", owner, 2026-10-22). This curve drops the faint fringe and lifts the rest; it was matched
# against the clock's own pixels. Never below 1: a fully transparent pixel lets clicks through.
_ALPHA_CURVE = [
    v if v <= 1 else max(1, min(255, round(255 * (max(0, v - 20) / 235) ** 0.75 * 1.15))) for v in range(256)
]


def _thicken_text(image: Image.Image) -> Image.Image:
    image.putalpha(image.getchannel("A").point(_ALPHA_CURVE))
    return image


def premultiplied_bgra(image: Image.Image) -> bytes:
    """The pixel format UpdateLayeredWindow wants: premultiplied alpha, BGRA byte order."""
    return image.convert("RGBa").tobytes("raw", "BGRa")
