"""Cartoon collider event displays: beams collide, tracks curl out, the signal is highlighted.

Not a physics simulation - just enough to be recognisable on 44x11 LEDs:

* charged tracks are arcs (curvature sign = charge, |curvature| ~ 1/pT);
  soft pile-up tracks curl tightly and stop early,
* muons are long, nearly straight tracks that leave the display,
* photons leave no track: they are drawn dotted and end in a 2x2 "calorimeter"
  deposit,
* jets are narrow sprays of tracks.

The view is a side view with the beams running left-right through the centre.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from PIL import Image

from .font import render_text
from .protocol import HEIGHT, WIDTH
from .render import blank

CX, CY = WIDTH / 2 - 0.5, HEIGHT // 2   # interaction point (between columns 21 and 22, row 5)
GROW = 2.2                              # track growth, px per frame


@dataclass
class Track:
    angle: float          # initial direction (radians, 0 = right)
    curvature: float      # radians per px, sign = charge
    length: float         # max path length (px); stops earlier at the display edge
    kind: str = "track"   # "track", "muon" or "photon"
    signal: bool = False

    def pixels(self) -> list[tuple[int, int, float]]:
        """(x, y, path length) of each new pixel along the track, in order."""
        out: list[tuple[int, int, float]] = []
        x, y, phi, s = CX, CY, self.angle, 0.0
        while s < self.length:
            x += 0.5 * math.cos(phi)
            y -= 0.5 * math.sin(phi)      # screen y points down
            phi += 0.5 * self.curvature
            s += 0.5
            p = (round(x), round(y))
            if not (0 <= p[0] < WIDTH and 0 <= p[1] < HEIGHT):
                break
            if not out or out[-1][:2] != p:
                out.append((*p, s))
        return out


def _forward_angle(rng: random.Random, max_deg: float = 32) -> float:
    """A direction within ``max_deg`` of the beam line (long, visible tracks), left or right."""
    a = math.radians(rng.uniform(-max_deg, max_deg))
    return a if rng.random() < 0.5 else math.pi + a


def _back_to_back(rng: random.Random) -> tuple[float, float]:
    a = _forward_angle(rng)
    return a, a + math.pi + math.radians(rng.uniform(-12, 12))


def _pileup(rng: random.Random) -> list[Track]:
    return [Track(rng.uniform(0, 2 * math.pi), rng.choice([-1, 1]) * rng.uniform(0.15, 0.35),
                  rng.uniform(3, 9)) for _ in range(rng.randint(2, 4))]


def _muon(angle: float, charge: int, rng: random.Random) -> Track:
    return Track(angle, charge * rng.uniform(0.006, 0.02), 99, "muon", True)


def _jet(axis: float, rng: random.Random) -> list[Track]:
    return [Track(axis + rng.uniform(-0.15, 0.15), rng.choice([-1, 1]) * rng.uniform(0.0, 0.04),
                  rng.uniform(14, 99), "track", True) for _ in range(rng.randint(2, 3))]


def _hgg(rng):
    a, b = _back_to_back(rng)
    return [Track(a, 0, 99, "photon", True), Track(b, 0, 99, "photon", True)]


def _zmumu(rng):
    a, b = _back_to_back(rng)
    q = rng.choice([-1, 1])
    return [_muon(a, q, rng), _muon(b, -q, rng)]


def _h4mu(rng):
    a, b = _back_to_back(rng)
    c, d = _back_to_back(rng)
    return [_muon(a, 1, rng), _muon(b, -1, rng), _muon(c, 1, rng), _muon(d, -1, rng)]


def _dijet(rng):
    a, b = _back_to_back(rng)
    return _jet(a, rng) + _jet(b, rng)


EVENTS = {
    # name: (label shown after the event, signal generator)
    "hgg": ("H→γγ", _hgg),
    "zmumu": ("Z→μμ", _zmumu),
    "h4mu": ("H→4μ", _h4mu),
    "dijet": ("dijet", _dijet),
}


def _draw(tracks: list[Track], reach: float, img: Image.Image | None = None) -> Image.Image:
    """Draw every track up to path length ``reach`` (plus photon calorimeter hits)."""
    img = img or blank()
    px = img.load()
    for t in tracks:
        pts = t.pixels()
        for i, (x, y, s) in enumerate(pts):
            if s > reach:
                break
            if t.kind != "photon" or i % 2 == 0:
                px[x, y] = 1
        else:
            if t.kind == "photon" and pts:      # reached the edge: calorimeter deposit
                x, y, _ = pts[-1]
                for dx in (0, -1 if x > CX else 1):
                    for dy in (0, -1 if y > CY else 1):
                        if 0 <= x + dx < WIDTH and 0 <= y + dy < HEIGHT:
                            px[x + dx, y + dy] = 1
    px[int(CX), CY] = px[int(CX) + 1, CY] = 1   # the vertex
    return img


def event_frames(event: str, rng: random.Random, label: bool = True) -> list[Image.Image]:
    """Frames for one event: beams in, flash, tracks grow, hold, highlight signal, label."""
    name, make_signal = EVENTS[event]
    signal = make_signal(rng)
    tracks = signal + _pileup(rng)
    frames = []
    # beams: two short bunches meeting at the interaction point
    for k in range(10):
        img = blank()
        px = img.load()
        for x in (2 * k, 2 * k + 1, WIDTH - 1 - 2 * k, WIDTH - 2 - 2 * k):
            px[x, CY] = 1
        frames.append(img)
    # collision flash
    for r in (1, 2):
        img = blank()
        px = img.load()
        for d in range(-r, r + 1):
            for x, y in ((int(CX) + d, CY), (int(CX) + 1 + d, CY), (int(CX), CY + d), (int(CX) + 1, CY + d),
                         (int(CX) + d, CY + d), (int(CX) + 1 - d, CY + d)):
                if 0 <= x < WIDTH and 0 <= y < HEIGHT:
                    px[x, y] = 1
        frames.append(img)
    # tracks grow outwards until every track has reached its end
    longest = max((p[-1][2] for t in tracks if (p := t.pixels())), default=0)
    steps = math.ceil(longest / GROW)
    frames += [_draw(tracks, (k + 1) * GROW) for k in range(steps)]
    full = _draw(tracks, 1e9)
    frames += [full] * 5
    # highlight: pile-up blinks off so the signal stands out
    sig = _draw(signal, 1e9)
    frames += [sig, sig, full, full] * 2 + [sig] * 3
    if label:
        frames += [render_text(name, min_width=WIDTH)] * 10
    frames += [blank()] * 2
    return frames


def collision(events: list[str] | None = None, seed: int | None = None,
              label: bool = True) -> tuple[list[Image.Image], int]:
    """Frames for a sequence of events (default: H→γγ then Z→μμ).

    Returns:
        (frames, seed_used)
    """
    events = events or ["hgg", "zmumu"]
    unknown = [e for e in events if e not in EVENTS]
    if unknown:
        raise ValueError(f"unknown event(s) {unknown}; choose from {', '.join(EVENTS)}")
    seed = random.randrange(1 << 30) if seed is None else seed
    rng = random.Random(seed)
    frames = []
    for e in events:
        frames += event_frames(e, rng, label)
    return frames, seed
