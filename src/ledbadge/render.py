"""Helpers to turn images/frames into badge bitmaps and to preview them."""

from __future__ import annotations

from collections.abc import Iterable

from PIL import Image, ImageOps, ImageSequence

from .protocol import FRAME_WIDTH, HEIGHT, WIDTH


def blank(width: int = WIDTH) -> Image.Image:
    """An all-off 1-bit image of the badge height."""
    return Image.new("1", (width, HEIGHT), 0)


def image_to_bitmap(img: Image.Image, width: int | None = None, dither: bool = True,
                    invert: bool = False, threshold: int = 128) -> Image.Image:
    """Convert an arbitrary image to an 11-px-high 1-bit bitmap.

    Args:
        img: Source image (any mode). Transparent pixels count as dark.
        width: Target width; ``None`` keeps the aspect ratio.
        dither: Floyd-Steinberg dithering (good for photos); otherwise threshold.
        invert: Swap on/off (useful for dark-on-light artwork).
        threshold: Grey level (0-255) above which a pixel is on, if not dithering.
    """
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
        img = Image.alpha_composite(bg, img)
    grey = img.convert("L")
    if width is None:
        width = max(1, round(grey.width * HEIGHT / grey.height))
    grey = grey.resize((width, HEIGHT), Image.Resampling.LANCZOS)
    if invert:
        grey = ImageOps.invert(grey)
    if dither:
        return grey.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    return grey.point(lambda v: 255 if v >= threshold else 0).convert("1")


def fit_frame(img: Image.Image, width: int = WIDTH) -> Image.Image:
    """Crop/pad a bitmap to exactly ``width`` columns, centred."""
    out = blank(width)
    out.paste(img.convert("1"), ((width - img.width) // 2, 0))
    return out


def animation_strip(frames: Iterable[Image.Image], frame_offset: int = 2) -> Image.Image:
    """Concatenate 44-px frames into an animation-mode strip of 48-px frames.

    Animation mode consumes 48 columns per frame but the display only shows 44;
    ``frame_offset`` is where the visible window starts within each 48-px frame
    (2 = centred; check with ``badge test frame`` on your hardware).
    """
    frames = [fit_frame(f) for f in frames]
    strip = blank(FRAME_WIDTH * len(frames))
    for i, f in enumerate(frames):
        strip.paste(f, (i * FRAME_WIDTH + frame_offset, 0))
    return strip


def gif_frames(img: Image.Image, dither: bool = True, invert: bool = False,
               max_frames: int | None = None) -> list[Image.Image]:
    """Convert every frame of an animated image to 44x11 bitmaps (aspect kept)."""
    frames = []
    for frame in ImageSequence.Iterator(img):
        f = frame.copy()
        f.thumbnail((WIDTH * 8, HEIGHT * 8))  # keep it small before resampling
        w = min(WIDTH, max(1, round(f.width * HEIGHT / f.height)))
        frames.append(fit_frame(image_to_bitmap(f, width=w, dither=dither, invert=invert)))
        if max_frames and len(frames) >= max_frames:
            break
    return frames


def ascii_preview(img: Image.Image, on: str = "█", off: str = "·") -> str:
    """Text rendering of a bitmap for terminal previews."""
    img = img.convert("1")
    px = img.load()
    return "\n".join("".join(on if px[x, y] else off for x in range(img.width))
                     for y in range(img.height))


def upscale_preview(img: Image.Image, scale: int = 10) -> Image.Image:
    """Make an LED-style RGB preview image (red dots on black)."""
    img = img.convert("1")
    out = Image.new("RGB", (img.width * scale, img.height * scale), (15, 15, 15))
    from PIL import ImageDraw
    d = ImageDraw.Draw(out)
    px = img.load()
    r = scale * 0.4
    for y in range(img.height):
        for x in range(img.width):
            cx, cy = x * scale + scale / 2, y * scale + scale / 2
            colour = (255, 40, 30) if px[x, y] else (50, 12, 10)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=colour)
    return out
