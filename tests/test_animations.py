"""Pong, rain, wave text and collider animations."""

import random

import pytest

from ledbadge import animations as A
from ledbadge import collider as C
from ledbadge.font import render_text
from ledbadge.protocol import HEIGHT, WIDTH, max_animation_frames


def lit(img):
    return {(x, y) for x in range(img.width) for y in range(img.height) if img.getpixel((x, y))}


def test_pong_rally_lengths_and_loop():
    # serve -> first paddle takes 21 frames, each extra return one 41-frame crossing
    lengths = [len(A._pong_run(7, r, net=False)) for r in range(4)]
    assert [b - a for a, b in zip(lengths, lengths[1:])] == [41, 41, 41]
    frames, seed = A.pong(seed=7, net=False)
    assert seed == 7 and len(frames) <= max_animation_frames()
    paddles_centred = {(0, 4), (0, 5), (0, 6), (WIDTH - 1, 4), (WIDTH - 1, 5), (WIDTH - 1, 6)}
    # loop point: last frame = centred paddles, no ball; first frame = same + ball at the centre
    assert lit(frames[-1]) == paddles_centred
    assert lit(frames[0]) == paddles_centred | {(WIDTH // 2 - 1, HEIGHT // 2)}
    assert all(f.size == (WIDTH, HEIGHT) for f in frames)


def test_pong_rally_too_long_rejected():
    with pytest.raises(ValueError):
        A.pong(seed=1, rally=6)


@pytest.mark.parametrize("n", [20, 60, 123])
def test_rain_loops_seamlessly(n):
    drops = A._rain_drops(n, 0.8, 3, random.Random(n))
    assert drops
    assert A._rain_frame(drops, n).tobytes() == A._rain_frame(drops, 0).tobytes()
    frames, _ = A.rain(n, seed=n)
    assert len(frames) == n


def test_wave_static_and_scrolling():
    frames = A.wave_text("Hi!", amplitude=0)
    assert len(frames) == 20
    # with no amplitude the letters sit one row lower than plain text (capitals centred)
    plain = {(x, y + 1) for x, y in lit(render_text("Hi!", min_width=WIDTH))}
    assert lit(frames[0]) == plain
    long = A.wave_text("A message that is much wider than the badge")
    assert 1 < len(long) <= max_animation_frames()
    assert not lit(long[0])                                     # starts just off the right edge
    assert min(x for x, _ in lit(long[1])) >= WIDTH - 3         # ...and enters from the right


@pytest.mark.parametrize("event", list(C.EVENTS))
def test_collider_event(event):
    frames = C.event_frames(event, random.Random(3))
    assert 30 < len(frames) < 70
    assert lit(frames[-3]) == lit(render_text(C.EVENTS[event][0], min_width=WIDTH))  # label
    assert not lit(frames[-1])                                                      # blank before loop


def test_collision_seeded_and_validated():
    a, s = C.collision(["hgg", "zmumu"], seed=11)
    b, _ = C.collision(["hgg", "zmumu"], seed=11)
    assert s == 11 and [f.tobytes() for f in a] == [f.tobytes() for f in b]
    assert len(a) <= max_animation_frames()
    with pytest.raises(ValueError):
        C.collision(["nope"])


def test_photons_end_in_calorimeter_block():
    t = C.Track(0.0, 0, 99, "photon", True)            # straight to the right edge
    img = C._draw([t], 1e9)
    assert {(WIDTH - 1, 5), (WIDTH - 2, 5), (WIDTH - 1, 6), (WIDTH - 2, 6)} <= lit(img)


@pytest.mark.parametrize("n", [30, 60, 123])
def test_binary_rain_loops_seamlessly(n):
    streams = A._binary_streams(n, 0.9, random.Random(n))
    assert streams
    for t in (0, 7):
        assert A._binary_frame(streams, t + n, n).tobytes() == A._binary_frame(streams, t, n).tobytes()
    frames, _ = A.binary_rain(n, seed=1)
    assert len(frames) == n and all(f.size == (WIDTH, HEIGHT) for f in frames)


def test_binary_rain_glyphs_are_digits():
    # a single stream frozen at a known position shows a whole 0 or 1
    stream = (0, 18, 0.0, 6.0, ["1", " ", " "], [0, 0, 0], [0, 0, 0])
    img = A._binary_frame([stream], 0, 60)
    assert lit(img) == {(c, r) for r, row in enumerate(A._BITS["1"]) for c, v in enumerate(row) if v == "#"}


def test_binary_rain_flip_option():
    on = A._binary_streams(60, 0.9, random.Random(5), flip=True)
    off = A._binary_streams(60, 0.9, random.Random(5), flip=False)
    # same streams and digits; only the flip schedule differs
    assert [s[:5] for s in on] == [s[:5] for s in off]
    assert all(f == 0 for s in off for f in s[5])
    flips = [f for s in on for f, b in zip(s[5], s[4]) if b != " "]
    assert set(flips) <= {0, 2} and 0 < sum(1 for f in flips if f) < len(flips) / 2


@pytest.mark.parametrize("seed", range(8))
def test_runner_never_hits_a_cactus_and_loops(seed):
    rng = random.Random(seed)
    n = 120
    world = A._runner_world(n, rng)
    gaps = {rng.randrange(n) for _ in range(n // 9)}
    assert world[0], "no cacti placed"
    for t in range(n):
        dino, cacti, ground = A._runner_layers(world, t, n, gaps)
        assert not (lit(dino) & lit(ground))
        assert not (lit(dino) & lit(cacti)), f"dino touches a cactus at frame {t}"
        assert all(y < HEIGHT - 1 for _, y in lit(dino))          # never sinks into the ground
    for a, b in zip(A._runner_layers(world, n, n, gaps), A._runner_layers(world, 0, n, gaps)):
        assert a.tobytes() == b.tobytes()


def test_runner_every_cactus_has_a_clearing_jump():
    assert all(A._plan_jump(rows) is not None for rows in A._CACTI.values())
    frames, _ = A.runner(seed=3)
    assert len(frames) == 120
    with pytest.raises(ValueError):
        A.runner(frames=122)
