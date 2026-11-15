"""Generated content: Game of Life, clocks and test patterns."""

from __future__ import annotations

import random
from datetime import datetime

from PIL import Image

from .font import render_text, text_width
from .protocol import HEIGHT, WIDTH
from .render import blank

Grid = list[list[int]]


# --- Game of Life -------------------------------------------------------------
def life_step(grid: Grid, wrap: bool = True) -> Grid:
    """One Conway generation on a HEIGHT x WIDTH grid (toroidal if ``wrap``)."""
    h, w = len(grid), len(grid[0])
    new = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            n = 0
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == dy == 0:
                        continue
                    yy, xx = y + dy, x + dx
                    if wrap:
                        yy, xx = yy % h, xx % w
                    elif not (0 <= yy < h and 0 <= xx < w):
                        continue
                    n += grid[yy][xx]
            new[y][x] = 1 if n == 3 or (n == 2 and grid[y][x]) else 0
    return new


def grid_to_image(grid: Grid) -> Image.Image:
    """Render a 0/1 grid as a 1-bit bitmap."""
    img = blank(len(grid[0]))
    px = img.load()
    for y, row in enumerate(grid):
        for x, v in enumerate(row):
            if v:
                px[x, y] = 1
    return img


def life_run(seed: int, density: float, max_frames: int, wrap: bool = True) -> list[Grid]:
    """Simulate from a random soup until extinction, a repeat, or ``max_frames``."""
    rng = random.Random(seed)
    grid = [[1 if rng.random() < density else 0 for _ in range(WIDTH)] for _ in range(HEIGHT)]
    seen: set[tuple] = set()
    states: list[Grid] = []
    while len(states) < max_frames:
        key = tuple(map(tuple, grid))
        if key in seen or not any(map(any, grid)):
            break
        seen.add(key)
        states.append(grid)
        grid = life_step(grid, wrap)
    return states


def game_of_life(max_frames: int, seed: int | None = None, density: float = 0.35,
                 tries: int = 200, wrap: bool = True) -> tuple[list[Image.Image], int]:
    """Pick the longest-lived random soup (up to ``max_frames`` generations).

    Many random soups die or freeze within a few dozen generations on such a
    small torus, so ``tries`` seeds are simulated and the longest is kept.

    Returns:
        (frames, seed_used)
    """
    if seed is not None:
        candidates = [seed]
    else:
        base = random.randrange(1 << 30)
        candidates = [base + i for i in range(tries)]
    best_seed, best = candidates[0], []
    for s in candidates:
        states = life_run(s, density, max_frames, wrap)
        if len(states) > len(best):
            best_seed, best = s, states
        if len(best) >= max_frames:
            break
    return [grid_to_image(g) for g in best], best_seed


# --- Clock ----------------------------------------------------------------------
def clock_frames(now: datetime | None = None, fmt: str = "%H:%M",
                 seconds_bar: int = 0, start_second: int = 0) -> list[Image.Image]:
    """Frames for a clock in the big digit font.

    Args:
        now: Time to show (default: now).
        fmt: ``strftime`` format; only digits, ``:``, ``-`` and spaces exist in
            the big font.
        seconds_bar: If > 0, produce this many frames for one minute with a
            seconds progress bar on the bottom row (colon blinks every other
            frame). If 0, produce two frames (colon on/off) for a 1 Hz blink.
        start_second: Seconds already elapsed in the current minute (bar start).
    """
    now = now or datetime.now()
    text = now.strftime(fmt)
    on = render_text(text, font="big", min_width=WIDTH)
    # blank the colon columns in place so the digits don't shift
    off = on.copy()
    x = (on.width - text_width(text, "big")) // 2
    for ch in text:
        w = text_width(ch, "big")
        if ch == ":":
            off.paste(0, (x, 0, x + w, HEIGHT))
        x += w + 1
    if seconds_bar <= 0:
        return [on, off]
    frames = []
    for i in range(seconds_bar):
        sec = start_second + 60 * i / seconds_bar
        f = (on if i % 2 == 0 else off).copy()
        px = f.load()
        for x in range(round(WIDTH * min(sec, 60) / 60)):
            px[x, HEIGHT - 1] = 1
        frames.append(f)
    return frames


# --- Test patterns -----------------------------------------------------------------
def test_frame_ruler() -> Image.Image:
    """48-px-wide frame with marks to find which 44 columns animation mode shows.

    Columns 0-3 and 44-47 have descending bars of height 1..4 (col 0 tallest),
    so the visible edge bars reveal the window offset.
    """
    img = Image.new("1", (48, HEIGHT), 0)
    px = img.load()
    for i in range(4):
        for y in range(HEIGHT - (4 - i) * 2, HEIGHT):
            px[i, y] = 1                 # left: cols 0..3, heights 8,6,4,2
        for y in range(HEIGHT - (i + 1) * 2, HEIGHT):
            px[44 + i, y] = 1            # right: cols 44..47, heights 2,4,6,8
    for x in range(48):
        px[x, 0] = 1
    return img


def test_border() -> Image.Image:
    """A 44x11 rectangle outline plus a diagonal, to check orientation/edges."""
    img = blank()
    px = img.load()
    for x in range(WIDTH):
        px[x, 0] = px[x, HEIGHT - 1] = 1
    for y in range(HEIGHT):
        px[0, y] = px[WIDTH - 1, y] = 1
        px[y, y] = 1
    return img
