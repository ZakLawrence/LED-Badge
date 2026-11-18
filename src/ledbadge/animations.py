"""Looping on-badge animations: self-playing Pong, digital rain and wave text.

Every generator returns a list of 44x11 1-bit frames for animation mode that
loops seamlessly (the state after the last frame is the first frame), and stays
within ``max_frames`` (default: everything the badge can hold in one message).
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageChops

from .font import render_text, text_width
from .protocol import HEIGHT, WIDTH, max_animation_frames
from .render import blank

PADDLE = 3


# --- Pong -----------------------------------------------------------------------------
def _bounce(y: float, vy: float) -> tuple[float, float]:
    """Reflect the ball off the top/bottom rows."""
    if y < 0:
        return -y, -vy
    if y > HEIGHT - 1:
        return 2 * (HEIGHT - 1) - y, -vy
    return y, vy


def _arrival_row(bx: int, by: float, vx: int, vy: float) -> int:
    """Row at which the ball will reach the paddle it is moving towards."""
    target = WIDTH - 2 if vx > 0 else 1
    while (target - bx) * vx > 0:   # stops immediately once the ball is past the paddle
        bx += vx
        by, vy = _bounce(by + vy, vy)
    return int(by + 0.5)


def _pong_run(seed: int, rally: int, net: bool) -> list[Image.Image]:
    """Simulate one point: serve from the centre, ``rally`` returns, a miss, reset."""
    rng = random.Random(seed)
    centre = (HEIGHT - PADDLE) // 2
    bx, by, vx = WIDTH // 2 - 1, float(HEIGHT // 2), 1
    vy = rng.choice([-0.5, 0.5])
    pad = {"left": centre, "right": centre}
    hits = 0
    frames: list[Image.Image] = []

    def draw(ball: bool) -> Image.Image:
        img = blank()
        px = img.load()
        if net:
            for y in range(0, HEIGHT, 2):
                px[WIDTH // 2, y] = 1
        for y in range(PADDLE):
            px[0, pad["left"] + y] = 1
            px[WIDTH - 1, pad["right"] + y] = 1
        if ball and 0 <= bx < WIDTH:
            px[bx, int(by + 0.5)] = 1
        return img

    def step_paddle(side: str, target: float) -> None:
        goal = max(0, min(HEIGHT - PADDLE, round(target)))
        pad[side] += (goal > pad[side]) - (goal < pad[side])

    while -1 <= bx <= WIDTH:
        frames.append(draw(ball=True))
        towards = "right" if vx > 0 else "left"
        away = "left" if towards == "right" else "right"
        arrive = _arrival_row(bx, by, vx, vy)
        if hits >= rally:   # this paddle is going to lose: get out of the ball's way
            step_paddle(towards, 0 if arrive >= HEIGHT / 2 else HEIGHT - PADDLE)
        else:               # meet the ball with the middle of the paddle
            step_paddle(towards, arrive - PADDLE // 2)
        step_paddle(away, centre)
        bx += vx
        by, vy = _bounce(by + vy, vy)
        for side, col, new_vx in (("left", 1, 1), ("right", WIDTH - 2, -1)):
            if bx == col and vx != new_vx and pad[side] <= int(by + 0.5) < pad[side] + PADDLE:
                offset = int(by + 0.5) - (pad[side] + 1)          # -1, 0, +1 on the paddle
                vy = max(-0.75, min(0.75, vy + 0.25 * offset + rng.choice([-0.25, 0, 0.25])))
                if vy == 0:
                    vy = rng.choice([-0.25, 0.25])
                vx = new_vx
                hits += 1
    # point scored: paddles recentre, then a short pause before the next serve
    while pad["left"] != centre or pad["right"] != centre:
        step_paddle("left", centre)
        step_paddle("right", centre)
        frames.append(draw(ball=False))
    frames += [draw(ball=False)] * 3
    return frames


def pong(seed: int | None = None, rally: int | None = None, net: bool = True,
         max_frames: int | None = None) -> tuple[list[Image.Image], int]:
    """Two computer paddles play one point; the loop restarts with the next serve.

    Args:
        seed: Randomises the ball angles.
        rally: Number of successful returns before the miss; ``None`` = as many
            as fit in ``max_frames`` (a full crossing takes 41 frames).
        net: Draw the dotted centre line.

    Returns:
        (frames, seed_used)
    """
    max_frames = max_frames or max_animation_frames()
    seed = random.randrange(1 << 30) if seed is None else seed
    for r in ([rally] if rally is not None else range(6, -1, -1)):
        frames = _pong_run(seed, r, net)
        if len(frames) <= max_frames:
            return frames, seed
    raise ValueError(f"pong needs {len(frames)} frames, only {max_frames} available")


# --- Digital rain -----------------------------------------------------------------------
Drop = tuple[int, int, float, float, int]   # (x, cycle, speed, phase, tail_len)


def _rain_drops(frames: int, density: float, tail: int, rng: random.Random) -> list[Drop]:
    """Random drops whose motion repeats exactly every ``frames`` frames.

    Each drop moves through ``cycle`` rows (the display plus an off-screen gap)
    an integer number of times per loop, which makes the loop seamless.
    """
    drops = []
    for x in range(WIDTH):
        if rng.random() > density:
            continue
        cycle = rng.randint(HEIGHT + tail + 2, 2 * HEIGHT + 6)
        # integer number of cycles per loop, at a speed between ~0.3 and ~1.2 rows/frame
        laps = [k for k in range(1, 20) if 0.3 <= k * cycle / frames <= 1.2]
        if laps:
            speed = rng.choice(laps) * cycle / frames
            drops.append((x, cycle, speed, rng.uniform(0, cycle), rng.randint(1, max(tail, 1))))
    return drops


def _rain_frame(drops: list[Drop], t: int) -> Image.Image:
    img = blank()
    px = img.load()
    for x, cycle, speed, phase, length in drops:
        head = int(round((phase + speed * t) % cycle, 9))   # round: avoid float jitter at the wrap
        for i in range(length + 1):
            if 0 <= head - i < HEIGHT:
                px[x, head - i] = 1
    return img


def rain(frames: int = 60, density: float = 0.7, tail: int = 3,
         seed: int | None = None) -> tuple[list[Image.Image], int]:
    """Falling drops with tails ("digital rain"), looping exactly every ``frames`` frames.

    Returns:
        (frames, seed_used)
    """
    if not 2 <= frames <= max_animation_frames():
        raise ValueError(f"frames must be 2..{max_animation_frames()}")
    seed = random.randrange(1 << 30) if seed is None else seed
    drops = _rain_drops(frames, density, tail, random.Random(seed))
    return [_rain_frame(drops, t) for t in range(frames)], seed


# --- Binary ("Matrix") rain --------------------------------------------------------------
_BITS = {"0": ["###", "#.#", "#.#", "#.#", "###"], "1": [".#.", "##.", ".#.", ".#.", "###"]}
_BIT_PITCH = 6      # 5-px glyph + 1-px gap, vertically
_BIT_COL = 4        # 3-px glyph + 1-px gap, horizontally -> 11 streams
FLIP_CHANCE = 0.15  # fraction of digits that flip 0<->1 (once each way per loop)
Stream = tuple[int, int, float, float, list[str], list[int], list[int]]


def _binary_streams(frames: int, density: float, rng: random.Random, flip: bool = True) -> list[Stream]:
    """Streams of 0/1 glyphs on a looping "tape" that moves an integer number of laps per loop.

    The tape is >= 3 glyphs long so a glyph wraps around only when fully off-screen.
    With ``flip``, a few glyphs flip 0<->1 and back once per loop (an even number of
    flips keeps the loop seamless). The random draws are the same either way, so a
    seed gives the same pattern with and without flips.
    """
    streams = []
    for i in range(WIDTH // _BIT_COL):
        if rng.random() > density:
            continue
        options = [(k, m) for k in range(3, 21) for m in range(1, 6)
                   if 0.25 <= m * k * _BIT_PITCH / frames <= 1.0]
        if not options:
            continue
        k, m = rng.choice(options)
        slots: list[str] = []
        while len(slots) < k:   # runs of 1-3 digits separated by 1-2 gaps
            slots += [rng.choice("01") for _ in range(rng.randint(1, 3))] + [" "] * rng.randint(1, 2)
        slots = slots[:k]
        if not slots[0].strip():
            slots[0] = rng.choice("01")
        flips = [2 if rng.random() < FLIP_CHANCE and flip else 0 for _ in slots]
        offsets = [rng.randrange(frames) for _ in slots]
        period = k * _BIT_PITCH
        streams.append((i * _BIT_COL, period, m * period / frames, rng.uniform(0, period),
                        slots, flips, offsets))
    return streams


def _binary_frame(streams: list[Stream], t: int, frames: int) -> Image.Image:
    img = blank()
    px = img.load()
    for x0, period, speed, phase, slots, flips, offsets in streams:
        shift = int(round((phase + speed * t) % period, 9))
        for j, bit in enumerate(slots):
            if bit == " ":
                continue
            if flips[j] and (t + offsets[j]) * flips[j] // frames % 2:
                bit = "1" if bit == "0" else "0"
            top = (j * _BIT_PITCH + shift) % period - _BIT_PITCH
            for r, row in enumerate(_BITS[bit]):
                if 0 <= top + r < HEIGHT:
                    for c, v in enumerate(row):
                        if v == "#":
                            px[x0 + c, top + r] = 1
    return img


def binary_rain(frames: int = 60, density: float = 0.8, seed: int | None = None,
                flip: bool = True) -> tuple[list[Image.Image], int]:
    """Falling streams of tiny 0/1 digits, Matrix style, looping every ``frames`` frames.

    Returns:
        (frames, seed_used)
    """
    if not 2 <= frames <= max_animation_frames():
        raise ValueError(f"frames must be 2..{max_animation_frames()}")
    seed = random.randrange(1 << 30) if seed is None else seed
    streams = _binary_streams(frames, density, random.Random(seed), flip)
    return [_binary_frame(streams, t, frames) for t in range(frames)], seed


# --- Endless runner (jump over cacti) -------------------------------------------------------
_DINO = {  # 6x6, facing right (head with eye, tail on the left); two leg poses for running
    "body": ["...###", "...#.#", "#..###", "#####.", ".###.."],
    "legs": [".#.#..", "..#.#."],
}
_CACTI = {  # name: rows (bottom row stands on the ground)
    "small": ["#.#", "###", ".#."],
    "tall": [".#.", "###", ".#.", ".#."],
    "twin": ["#...#", "##.##", ".#.#."],
}
_JUMP = [1, 2, 3, 4, 4, 4, 4, 4, 4, 4, 4, 3, 2, 1]   # dino lift (rows) per frame; 4 = head at row 0
_DINO_X, _GROUND = 3, HEIGHT - 1                     # dino column; ground row


def _plan_jump(rows: list[str]) -> int | None:
    """Offset (frames before the cactus reaches the dino's front) to start a clearing jump.

    The cactus scrolls 1 px/frame. While it overlaps the dino horizontally, the
    dino's lift must be at least the cactus height. Returns the offset that puts
    the overlap nearest the middle of the jump, or None if no jump clears it.
    """
    h, w, dw = len(rows), len(rows[0]), len(_DINO["body"][0])
    overlap = dw + w - 1
    best = None
    for start in range(len(_JUMP) - overlap + 1):
        if all(lift >= h for lift in _JUMP[start:start + overlap]):
            centred = abs(start + overlap / 2 - len(_JUMP) / 2)
            if best is None or centred < best[0]:
                best = (centred, start)
    return None if best is None else best[1]


def _runner_world(frames: int, rng: random.Random) -> tuple[list[tuple[int, str]], list[int]]:
    """Cacti (track position, type) on a ring of length ``frames``, plus jump start frames."""
    dw = len(_DINO["body"][0])
    cacti, jumps = [], []
    # first jump starts a little after frame 0; the ring must close with a gap before it
    jump_at = rng.randint(4, 14)
    first = jump_at
    while True:
        kind = rng.choice(list(_CACTI))
        lead = _plan_jump(_CACTI[kind])
        # the cactus reaches the dino's front edge `lead` frames into the jump
        hit = jump_at + lead
        pos = hit + _DINO_X + dw - 1       # track x such that screen x == dino front at t = hit
        if jump_at + len(_JUMP) + 3 > first + frames:   # would collide with the wrap-around
            break
        cacti.append((pos % frames, kind))
        jumps.append(jump_at)
        jump_at += len(_JUMP) + rng.randint(3, 22)
    return cacti, jumps


def _runner_lift(jumps: list[int], t: int, frames: int) -> int:
    for j in jumps:
        k = (t - j) % frames
        if k < len(_JUMP):
            return _JUMP[k]
    return 0


def _runner_layers(world, t: int, frames: int,
                   gaps: set[int]) -> tuple[Image.Image, Image.Image, Image.Image]:
    """(dino, cacti, ground) layers for frame ``t``; separate so tests can check for collisions."""
    cacti, jumps = world
    dino, prickly, scene = blank(), blank(), blank()
    dpx, cpx, spx = dino.load(), prickly.load(), scene.load()
    # ground: a line with a few gaps, scrolling 1 px/frame
    for x in range(WIDTH):
        if (x + t) % frames not in gaps:
            spx[x, _GROUND] = 1

    def stamp(px, rows, x0, y0):
        for r, row in enumerate(rows):
            for c, v in enumerate(row):
                if v == "#" and 0 <= x0 + c < WIDTH and 0 <= y0 + r < HEIGHT:
                    px[x0 + c, y0 + r] = 1

    for pos, kind in cacti:
        rows = _CACTI[kind]
        sx = (pos - t) % frames
        for x0 in (sx, sx - frames):     # also draw the copy sliding off the left edge
            stamp(cpx, rows, x0, _GROUND - len(rows))
    lift = _runner_lift(jumps, t, frames)
    legs = _DINO["legs"][0] if lift else _DINO["legs"][(t // 2) % 2]
    stamp(dpx, _DINO["body"] + [legs], _DINO_X, _GROUND - len(_DINO["body"]) - 1 - lift)
    return dino, prickly, scene


def runner(frames: int = 120, seed: int | None = None) -> tuple[list[Image.Image], int]:
    """Endless-runner loop: a dino jumps over scrolling cacti (like the offline game in Chrome).

    ``frames`` must be a multiple of 4 (the leg cycle) and fits the
    badge at <= 123; the world is a ring of that many pixels, so the loop is seamless.

    Returns:
        (frames, seed_used)
    """
    if frames % 4 or not 40 <= frames <= max_animation_frames():
        raise ValueError(f"frames must be a multiple of 4 in 40..{max_animation_frames()}")
    seed = random.randrange(1 << 30) if seed is None else seed
    rng = random.Random(seed)
    world = _runner_world(frames, rng)
    gaps = {rng.randrange(frames) for _ in range(frames // 9)}
    out = []
    for t in range(frames):
        dino, prickly, scene = _runner_layers(world, t, frames, gaps)
        out.append(ImageChops.logical_or(ImageChops.logical_or(dino, prickly), scene))
    return out, seed


# --- Wave text ------------------------------------------------------------------------
def wave_text(text: str, amplitude: float = 2.0, wavelength: float = 24.0,
              frames: int | None = None, max_frames: int | None = None) -> list[Image.Image]:
    """Text whose letters bob along a moving sine wave (classic demo-scene scroller).

    Text that fits on the display waves in place (``frames`` per wave cycle,
    default 20). Longer text scrolls right-to-left while waving, stepping
    1 px/frame, or more if needed to fit in ``max_frames``.
    """
    max_frames = max_frames or max_animation_frames()
    src = render_text(text)
    spx = src.load()
    tw = src.width
    if tw <= WIDTH:
        n = min(frames or 20, max_frames)
        positions = [(WIDTH - tw) // 2] * n
        cycles = 1
    else:
        distance = tw + WIDTH
        step = math.ceil(distance / max_frames)
        n = math.ceil(distance / step)
        positions = [WIDTH - t * step for t in range(n)]
        cycles = max(1, round(n / 16))
    # each letter moves as a whole, so glyphs stay readable
    spans, x = [], 0
    for ch in text:
        w = text_width(ch)
        spans.append((x, w))
        x += w + 1
    out = []
    for t, x0 in enumerate(positions):
        img = blank()
        px = img.load()
        phase = 2 * math.pi * cycles * t / n
        for start, w in spans:
            centre = x0 + start + w / 2
            # +1 centres the 7-px capitals (rows 1-7) on the 11-row display
            dy = 1 + round(amplitude * math.sin(2 * math.pi * centre / wavelength - phase))
            for cx in range(start, start + w):
                sx = x0 + cx
                if not 0 <= sx < WIDTH:
                    continue
                for y in range(HEIGHT):
                    if spx[cx, y] and 0 <= y + dy < HEIGHT:
                        px[sx, y + dy] = 1
        out.append(img)
    return out
