"""USB HID transport for the badge (VID 0x0416, PID 0x5020)."""

from __future__ import annotations

import time

import hid

VENDOR_ID = 0x0416
PRODUCT_ID = 0x5020
REPORT_SIZE = 64


class BadgeNotFound(RuntimeError):
    """Raised when no badge is attached over USB."""


def list_devices() -> list[dict]:
    """Return hidapi info dicts for every attached badge."""
    return hid.enumerate(VENDOR_ID, PRODUCT_ID)


def send(payload: bytes, path: bytes | None = None, delay: float = 0.0) -> float:
    """Write a payload (from :func:`ledbadge.protocol.build_payload`) to the badge.

    Args:
        payload: Bytes, length a multiple of 64.
        path: hidapi device path; defaults to the first badge found.
        delay: Optional pause between 64-byte reports (seconds).

    Returns:
        Time taken in seconds.
    """
    if len(payload) % REPORT_SIZE:
        raise ValueError("payload length must be a multiple of 64")
    devs = list_devices()
    if not devs:
        raise BadgeNotFound("no badge found on USB (0416:5020) - is it plugged in "
                            "with a data cable and switched on?")
    dev = hid.device()
    dev.open_path(path or devs[0]["path"])
    t0 = time.perf_counter()
    try:
        for i in range(0, len(payload), REPORT_SIZE):
            # First byte is the HID report ID (0 = unnumbered reports).
            n = dev.write(b"\x00" + payload[i:i + REPORT_SIZE])
            if n < 0:
                raise OSError(f"HID write failed: {dev.error()}")
            if delay:
                time.sleep(delay)
    finally:
        dev.close()
    return time.perf_counter() - t0
