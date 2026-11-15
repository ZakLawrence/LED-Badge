"""Protocol tests. Expected bytes follow fossasia/led-name-badge-ls32 lednamebadge.py."""

from datetime import datetime

import pytest
from PIL import Image

from ledbadge.effects import clock_frames, game_of_life, life_step
from ledbadge.font import FONTS, render_text
from ledbadge.protocol import (Message, Mode, build_header, build_payload, max_animation_frames,
                               pack_bitmap)
from ledbadge.render import animation_strip

WHEN = datetime(2026, 11, 15, 18, 30, 5)


def test_pack_bitmap_bit_order():
    img = Image.new("1", (9, 11), 0)
    img.putpixel((0, 0), 1)   # col block 0, row 0, MSB
    img.putpixel((7, 1), 1)   # col block 0, row 1, LSB
    img.putpixel((8, 10), 1)  # col block 1, row 10, MSB
    data, n = pack_bitmap(img)
    assert n == 2
    assert len(data) == 22
    assert data[0] == 0x80 and data[1] == 0x01 and data[11 + 10] == 0x80
    assert sum(data) == 0x80 + 0x01 + 0x80


def test_pack_rejects_wrong_height():
    with pytest.raises(ValueError):
        pack_bitmap(Image.new("1", (8, 12)))


def test_header_fields():
    img = Image.new("1", (16, 11))
    msgs = [Message(img, Mode.FIXED, speed=3, blink=True),
            Message(img, Mode.LASER, speed=8, marquee=True)]
    h = build_header(msgs, [2, 300], brightness=75, when=WHEN)
    assert len(h) == 64
    assert h[:6] == b"wang\x00\x10"
    assert h[6] == 0b01 and h[7] == 0b10
    assert h[8] == 0x24 and h[9] == 0x78       # 16*(speed-1)+mode
    assert list(h[10:16]) == [0x40] * 6         # unused slots keep the template default
    assert h[16:20] == bytes([0, 2, 1, 44])     # big-endian lengths
    assert h[38:44] == bytes([26, 11, 15, 18, 30, 5])


def test_payload_padding_and_limit():
    p = build_payload([Message(Image.new("1", (44, 11)))], when=WHEN)  # 64 + 6*11 -> 192
    assert len(p) == 192 and len(p) % 64 == 0
    n = max_animation_frames()
    ok = Message(Image.new("1", (48 * n, 11)), Mode.ANIMATION)
    assert len(build_payload([ok])) <= 8192
    with pytest.raises(ValueError):
        build_payload([Message(Image.new("1", (48 * (n + 1), 11)), Mode.ANIMATION)])


def test_fonts_well_formed():
    for name, (glyphs, top) in FONTS.items():
        for ch, g in glyphs.items():
            assert len(g) == 9 and len({len(r) for r in g}) == 1, (name, ch)
    img = render_text("Ag", min_width=44)
    assert img.size == (44, 11)


def test_life_blinker():
    g = [[0] * 5 for _ in range(5)]
    for x in (1, 2, 3):
        g[2][x] = 1
    g2 = life_step(g, wrap=False)
    assert [g2[y][2] for y in (1, 2, 3)] == [1, 1, 1] and sum(map(sum, g2)) == 3
    assert life_step(g2, wrap=False) == g


def test_life_and_clock_shapes():
    frames, _ = game_of_life(30, seed=1)
    assert 0 < len(frames) <= 30 and frames[0].size == (44, 11)
    strip = animation_strip(frames)
    assert strip.size == (48 * len(frames), 11)
    on, off = clock_frames(WHEN)
    assert on.size == off.size == (44, 11) and on.tobytes() != off.tobytes()
    assert len(clock_frames(WHEN, seconds_bar=120)) == 120
