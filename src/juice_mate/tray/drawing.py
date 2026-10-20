"""Draw a tray icon: the number on a coloured square (docs/architecture.md §6)."""

from PIL import Image, ImageDraw, ImageFont

from juice_mate.core.reading import Level

SIZE = 64

COLOURS: dict[Level, str] = {
    Level.OK: "#2e7d32",
    Level.LOW: "#c62828",
    Level.CHARGING: "#1565c0",
    Level.OFFLINE: "#757575",
    Level.UNKNOWN: "#757575",
}


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    # Segoe UI Bold ships with every Windows; elsewhere (CI, tests) fall back to Pillow's own font.
    try:
        return ImageFont.truetype("segoeuib.ttf", size)
    except OSError:
        return ImageFont.load_default(size)


def draw(text: str, lvl: Level) -> Image.Image:
    """A SIZE×SIZE RGBA image; Windows scales it down to the tray size."""
    image = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    canvas = ImageDraw.Draw(image)
    canvas.rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=12, fill=COLOURS[lvl])
    # Three digits ("100") need a smaller font to fit.
    font = _font(30 if len(text) > 2 else 40)
    canvas.text((SIZE / 2, SIZE / 2), text, font=font, fill="white", anchor="mm")
    if lvl is Level.CHARGING:
        canvas.polygon([(48, 2), (40, 16), (46, 16), (42, 28), (54, 12), (48, 12), (52, 2)], fill="#ffeb3b")
    return image
