"""Generate the Windows icon set from the single master PNG.

The project keeps two icon files at its root and nothing else: the master
`EDColonisationAsst.png`, which is what the application shows in its own
windows, and `EDColonisationAsst.ico`, which is what the PE build, the
shortcuts and the tray use. This script derives the second from the first, and
gives the first a transparent background if it arrived without one.

The badge is never resampled. Artwork that arrives flattened onto a background
is fixed by clearing that background, and a canvas that is not square is fixed
by padding it, so every pixel of the badge survives exactly as drawn. The only
resampling here is the downscale into the icon frames, which is unavoidable.
Enlarging artwork to fill a canvas is specifically what this script must never
do: this badge carries fine chrome lettering and an upscale leaves it soft and
grey-fringed.

Clearing the background is a flood fill inwards from the border rather than a
colour match across the whole image. That distinction matters here, because
the badge is a photograph of space and its interior is full of pixels as dark
as the background; matching on colour alone would punch holes through it. The
fill stops at the badge's own edge, so the interior is never reached.

The edge itself gets one more step. The artwork was flattened onto black, so
its anti-aliased rim is a blend of badge colour and black. Making those pixels
either fully opaque or fully transparent would leave a dark halo or a chewed
edge, so the rim is recovered instead: its alpha is read back out of its
brightness and its colour is unpremultiplied to match.

Run it after replacing the master artwork:

    python generate_icons.py
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent

MASTER_PNG = PROJECT_ROOT / "EDColonisationAsst.png"
ICO_FILE = PROJECT_ROOT / "EDColonisationAsst.ico"

# The GitHub Pages site carries its own copy, used as the favicon and as the
# logo in the page header. Written from here so that replacing the artwork
# cannot leave the site showing the previous icon.
SITE_ICON = PROJECT_ROOT / "docs" / "assets" / "edca-icon.png"
SITE_ICON_SIZE = 256

# The card social platforms unfurl for a link to the site. It is the badge on
# the site's own background rather than a cropped screenshot of the running
# application: a screenshot is unreadable at the size these are shown and goes
# stale every time the interface changes, whereas the badge already carries the
# product name and cannot drift.
#
# The badge is pasted at whatever size the master arrives at and is never
# enlarged to fill more of the card, for the reason the module docstring gives:
# this artwork is fine chrome lettering and an upscale turns it to grey mush.
# A bigger master is therefore the only way to make the badge bigger here.
SOCIAL_CARD = PROJECT_ROOT / "docs" / "assets" / "social-card.png"

# 1200x630 is what the og:image tags on every page of the site declare, and the
# 1.91:1 ratio the platforms crop to.
SOCIAL_CARD_SIZE = (1200, 630)

# Straight from docs/assets/site.css, so the card and the page it links to are
# the same object: --bg, --accent and --muted.
SOCIAL_BACKGROUND = (0x0F, 0x10, 0x13)
SOCIAL_ACCENT = (0xEE, 0x6B, 0x1C)
SOCIAL_STRAPLINE_COLOUR = (0x95, 0x95, 0x9F)

# The site draws a fading accent hairline across the top of every page
# (body::before). The card carries the same one.
SOCIAL_RULE_HEIGHT = 3

# One line, and deliberately not the product name: the badge says that already.
SOCIAL_STRAPLINE = "What still needs hauling, and where to."
SOCIAL_STRAPLINE_SIZE = 34

# The gap between the badge and the strapline, and between the strapline and
# the bottom edge. The badge is then centred in whatever height is left, so the
# layout holds if the master is replaced with a larger one.
SOCIAL_STRAPLINE_GAP = 46
SOCIAL_BOTTOM_MARGIN = 64

# Segoe UI is the site's first named sans after system-ui, so the card matches
# what a Windows reader sees on the page itself.
SOCIAL_FONT_CANDIDATES = (
    Path("C:/Windows/Fonts/segoeui.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)

HALF = 2

# A pixel this dark or darker, reachable from the border, is background.
BACKGROUND_MAX = 8

# The rim band. A pixel brighter than this is badge, whatever it touches; below
# it, brightness is read as coverage instead.
RIM_MAX = 72

# How far the rim treatment reaches in from the cleared background.
RIM_DEPTH = 2

OPAQUE = 255

# Every size Windows picks between: Explorer, the tray, the Alt-Tab switcher
# and the Apps list all resolve to different ones of these.
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

RGB = "RGB"
RGBA = "RGBA"
PREMULTIPLIED = "RGBa"
TRANSPARENT = (0, 0, 0, 0)


def _brightness(pixel: tuple[int, int, int, int]) -> int:
    """Return the pixel's strongest colour channel."""
    return max(pixel[0], pixel[1], pixel[2])


def has_transparency(image: Image.Image) -> bool:
    """Whether the image already carries a transparent background."""
    minimum, _maximum = image.getchannel("A").getextrema()
    return minimum < OPAQUE


def _flood_background(image: Image.Image) -> set[tuple[int, int]]:
    """Return the background pixels reachable inwards from the border."""
    width, height = image.size
    pixels = image.load()
    found: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    for x in range(width):
        queue.append((x, 0))
        queue.append((x, height - 1))
    for y in range(height):
        queue.append((0, y))
        queue.append((width - 1, y))

    while queue:
        x, y = queue.popleft()
        if not (0 <= x < width and 0 <= y < height) or (x, y) in found:
            continue
        if _brightness(pixels[x, y]) > BACKGROUND_MAX:
            continue
        found.add((x, y))
        queue.extend(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

    return found


def _rim(
    image: Image.Image,
    background: set[tuple[int, int]],
) -> set[tuple[int, int]]:
    """Return the partially covered pixels just inside the background."""
    width, height = image.size
    pixels = image.load()
    band: set[tuple[int, int]] = set()
    frontier = background

    for _ in range(RIM_DEPTH):
        neighbours: set[tuple[int, int]] = set()
        for x, y in frontier:
            neighbours.update(((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)))

        frontier = set()
        for x, y in neighbours:
            if not (0 <= x < width and 0 <= y < height):
                continue
            if (x, y) in background or (x, y) in band:
                continue
            if _brightness(pixels[x, y]) > RIM_MAX:
                continue
            band.add((x, y))
            frontier.add((x, y))

    return band


def clear_background(image: Image.Image) -> Image.Image:
    """Replace the flat background behind the badge with transparency."""
    cleared = image.copy()
    pixels = cleared.load()

    background = _flood_background(cleared)
    band = _rim(cleared, background)

    for x, y in background:
        pixels[x, y] = TRANSPARENT

    for x, y in band:
        red, green, blue, _alpha = pixels[x, y]
        coverage = _brightness((red, green, blue, 0)) / RIM_MAX
        alpha = round(OPAQUE * coverage)
        if alpha <= 0:
            pixels[x, y] = TRANSPARENT
            continue
        # The rim was flattened onto black, so its colour arrives already
        # multiplied by its own coverage. Undo that, or the edge stays dark.
        scale = OPAQUE / alpha
        pixels[x, y] = (
            min(OPAQUE, round(red * scale)),
            min(OPAQUE, round(green * scale)),
            min(OPAQUE, round(blue * scale)),
            alpha,
        )

    return cleared


def square(image: Image.Image) -> Image.Image:
    """Pad the image to a square canvas, centred, without resampling."""
    side = max(image.size)
    if image.size == (side, side):
        return image

    canvas = Image.new(RGBA, (side, side), TRANSPARENT)
    canvas.paste(
        image,
        ((side - image.width) // 2, (side - image.height) // 2),
    )
    return canvas


def _scaled(image: Image.Image, size: int) -> Image.Image:
    """Return the image at the given size, without bleeding the edges.

    Resampling straight RGBA mixes the colour of fully transparent pixels
    into its neighbours, which on this artwork means black seeping back into
    the rim the step above just cleaned. Premultiplying first prevents it.
    """
    premultiplied = image.convert(PREMULTIPLIED)
    resized = premultiplied.resize((size, size), Image.Resampling.LANCZOS)
    return resized.convert(RGBA)


def write_ico(image: Image.Image) -> None:
    """Write the multi-size Windows icon beside the master.

    Each frame is scaled here rather than left to the ICO writer, so that the
    premultiplied path above is the one every size goes through.
    """
    frames = [_scaled(image, size) for size in sorted(ICO_SIZES, reverse=True)]
    largest, *rest = frames
    largest.save(
        ICO_FILE,
        format="ICO",
        sizes=[frame.size for frame in frames],
        append_images=rest,
    )


def _strapline_font() -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Return the card's text font, falling back to Pillow's own."""
    for candidate in SOCIAL_FONT_CANDIDATES:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), SOCIAL_STRAPLINE_SIZE)
    return ImageFont.load_default()


def _accent_hairline(card: Image.Image) -> None:
    """Draw the site's fading accent rule across the top of the card."""
    draw = ImageDraw.Draw(card)
    midpoint = card.width / HALF
    for x in range(card.width):
        # Background at both edges, full accent in the middle, which is what
        # the CSS gradient on the page does.
        coverage = 1 - abs(x - midpoint) / midpoint
        blended = tuple(
            round(background + (accent - background) * coverage)
            for background, accent in zip(SOCIAL_BACKGROUND, SOCIAL_ACCENT, strict=True)
        )
        draw.line(((x, 0), (x, SOCIAL_RULE_HEIGHT - 1)), fill=blended)


def write_social_card(badge: Image.Image) -> None:
    """Write the link-preview card: the badge on the site's own background."""
    card = Image.new(RGB, SOCIAL_CARD_SIZE, SOCIAL_BACKGROUND)
    _accent_hairline(card)

    draw = ImageDraw.Draw(card)
    font = _strapline_font()
    left, top, right, bottom = draw.textbbox((0, 0), SOCIAL_STRAPLINE, font=font)
    strapline_y = card.height - SOCIAL_BOTTOM_MARGIN - (bottom - top)

    # The badge is centred in whatever height is left above the strapline. A
    # master too tall for that space is scaled DOWN to fit, which costs nothing;
    # one that is smaller is left exactly as drawn rather than enlarged.
    available = strapline_y - SOCIAL_STRAPLINE_GAP
    if badge.height > available:
        badge = _scaled(badge, available)

    card.paste(
        badge,
        ((card.width - badge.width) // HALF, (available - badge.height) // HALF),
        badge,
    )
    draw.text(
        ((card.width - (right - left)) // HALF - left, strapline_y - top),
        SOCIAL_STRAPLINE,
        font=font,
        fill=SOCIAL_STRAPLINE_COLOUR,
    )
    card.save(SOCIAL_CARD, format="PNG", optimize=True)


def main() -> int:
    """Prepare the master and regenerate the icon. Returns an exit code."""
    if not MASTER_PNG.exists():
        print(f"Master artwork not found: {MASTER_PNG}", file=sys.stderr)
        return 1

    with Image.open(MASTER_PNG) as opened:
        master = opened.convert(RGBA)

    print(f"Master read at {master.width}x{master.height}")

    if has_transparency(master):
        print("Background is already transparent; left as is.")
    else:
        master = clear_background(master)
        print(f"Background cleared below brightness {BACKGROUND_MAX}")

    squared = square(master)
    if squared.size != master.size:
        print(f"Padded to a square {squared.width}x{squared.height} canvas")
    master = squared

    master.save(MASTER_PNG, format="PNG", optimize=True)
    write_ico(master)

    print(f"Wrote {MASTER_PNG.name}")
    print(f"Wrote {ICO_FILE.name} at sizes {', '.join(str(s) for s in ICO_SIZES)}")

    if SITE_ICON.parent.is_dir():
        _scaled(master, SITE_ICON_SIZE).save(SITE_ICON, format="PNG", optimize=True)
        print(f"Wrote {SITE_ICON.relative_to(PROJECT_ROOT)} at {SITE_ICON_SIZE}px")

        write_social_card(master)
        card_width, card_height = SOCIAL_CARD_SIZE
        print(
            f"Wrote {SOCIAL_CARD.relative_to(PROJECT_ROOT)} "
            f"at {card_width}x{card_height} with the badge at {master.width}px"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
