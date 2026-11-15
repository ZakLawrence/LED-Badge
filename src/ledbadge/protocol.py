"""Badge Magic / LSLED "wang" upload protocol.

Payload layout (verified against fossasia/led-name-badge-ls32, lednamebadge.py):

* 64-byte header
    - 0..5   ``b"wang\\0"`` + brightness byte (0x00=100%, 0x10=75%, 0x20=50%, 0x40=25%)
    - 6      blink bit-mask (bit i -> message i)
    - 7      marquee ("ants") bit-mask
    - 8..15  per message: ``16 * (speed - 1) + mode``
    - 16..31 per message: length in 8-px "byte-columns", big endian u16
    - 38..43 timestamp yy mm dd HH MM SS (not displayed)
* bitmap data: for each message, for each 8-px column block, 11 bytes (one
  per row, MSB = leftmost pixel)
* zero padding to a multiple of 64 bytes; total must be <= 8192 bytes.

The badge stores up to 8 messages and cycles through them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum

from PIL import Image

HEIGHT = 11
WIDTH = 44           # visible columns
FRAME_WIDTH = 48     # animation-mode frame width (6 byte-columns)
MAX_MESSAGES = 8
MAX_PAYLOAD = 8192
HEADER_SIZE = 64
BLOCK = 64


class Mode(IntEnum):
    """Display modes. Names follow the Badge Magic app where they differ."""
    LEFT = 0
    RIGHT = 1
    UP = 2
    DOWN = 3
    FIXED = 4
    ANIMATION = 5
    SNOWFLAKE = 6   # "drop-down"
    PICTURE = 7     # "curtain"
    LASER = 8


_BRIGHTNESS = {25: 0x40, 50: 0x20, 75: 0x10, 100: 0x00}


@dataclass
class Message:
    """One of the badge's 8 message slots.

    Attributes:
        bitmap: 1-bit (or convertible) image, 11 px high, any width.
        mode: Scroll/display mode.
        speed: 1 (slow) .. 8 (fast). In animation mode ~1.2..15 fps.
        blink: Blink the whole message.
        marquee: Animated border ("ants").
    """
    bitmap: Image.Image
    mode: Mode = Mode.LEFT
    speed: int = 4
    blink: bool = False
    marquee: bool = False


def pack_bitmap(img: Image.Image) -> tuple[bytes, int]:
    """Pack an 11-px-high image into badge byte-columns.

    Pixels are "on" when non-zero after conversion to mode ``"1"``. The width
    is padded with blank columns up to a multiple of 8.

    Returns:
        (data, n_byte_columns)
    """
    if img.height != HEIGHT:
        raise ValueError(f"bitmap must be {HEIGHT} px high, got {img.height}")
    img = img.convert("1")
    px = img.load()
    ncols = (img.width + 7) // 8
    out = bytearray()
    for col in range(ncols):
        for row in range(HEIGHT):
            byte = 0
            for bit in range(8):
                x = col * 8 + bit
                if x < img.width and px[x, row]:
                    byte |= 0x80 >> bit
            out.append(byte)
    return bytes(out), ncols


def build_header(messages: list[Message], lengths: list[int],
                 brightness: int = 100, when: datetime | None = None) -> bytes:
    """Build the 64-byte protocol header."""
    if brightness not in _BRIGHTNESS:
        raise ValueError("brightness must be one of 25, 50, 75, 100")
    when = when or datetime.now()
    h = bytearray(HEADER_SIZE)
    h[0:4] = b"wang"
    h[5] = _BRIGHTNESS[brightness]
    for i in range(MAX_MESSAGES):
        h[8 + i] = 0x40  # default: speed 5, mode left (matches reference)
    for i, (msg, length) in enumerate(zip(messages, lengths)):
        if not 1 <= msg.speed <= 8:
            raise ValueError("speed must be 1..8")
        h[6] |= int(msg.blink) << i
        h[7] |= int(msg.marquee) << i
        h[8 + i] = 16 * (msg.speed - 1) + int(msg.mode)
        h[16 + 2 * i] = length >> 8
        h[17 + 2 * i] = length & 0xFF
    h[38:44] = bytes([when.year % 100, when.month, when.day,
                      when.hour, when.minute, when.second])
    return bytes(h)


def build_payload(messages: list[Message], brightness: int = 100,
                  when: datetime | None = None) -> bytes:
    """Build the full upload payload (header + bitmaps + padding).

    Raises:
        ValueError: if there are no/too many messages or the payload exceeds
            the badge's 8 KiB buffer.
    """
    if not 1 <= len(messages) <= MAX_MESSAGES:
        raise ValueError(f"need 1..{MAX_MESSAGES} messages, got {len(messages)}")
    packed = [pack_bitmap(m.bitmap) for m in messages]
    data = build_header(messages, [n for _, n in packed], brightness, when)
    data += b"".join(d for d, _ in packed)
    data += bytes(-len(data) % BLOCK)
    if len(data) > MAX_PAYLOAD:
        raise ValueError(f"payload is {len(data)} bytes, badge limit is {MAX_PAYLOAD}")
    return data


def max_animation_frames(n_other_columns: int = 0) -> int:
    """How many 48-px animation frames fit, given other messages' byte-columns."""
    free = MAX_PAYLOAD - HEADER_SIZE - HEIGHT * n_other_columns
    return free // (HEIGHT * FRAME_WIDTH // 8)
