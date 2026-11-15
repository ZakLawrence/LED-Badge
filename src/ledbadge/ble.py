"""Bluetooth LE transport (badge advertises as ``LSLED`` with service 0xFEE0).

The payload is the same as over USB; it is written to characteristic 0xFEE1 in
16-byte chunks (as the Badge Magic app does), with write-with-response so each
chunk is acknowledged before the next.

Stock-firmware behaviour observed on a CH583 badge: the badge drops the
connection as soon as it has received all the bitmap data announced in the
header (so writes of the trailing zero padding fail), and it then stops
advertising until BLE is re-enabled from the button. One upload per button
press, therefore.
"""

from __future__ import annotations

import asyncio
import time

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

DEFAULT_NAME = "LSLED"
SERVICE_UUID = "0000fee0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000fee1-0000-1000-8000-00805f9b34fb"
CHUNK = 16


class BadgeNotFound(RuntimeError):
    """Raised when no badge is advertising over BLE."""


def required_bytes(payload: bytes) -> int:
    """Header + bitmap bytes announced in the header (i.e. excluding padding)."""
    n_cols = sum(int.from_bytes(payload[16 + 2 * i:18 + 2 * i], "big") for i in range(8))
    return 64 + 11 * n_cols


async def scan(timeout: float = 5.0) -> list[tuple[BLEDevice, int]]:
    """Return (device, rssi) for every advertiser exposing the badge service."""
    found = await BleakScanner.discover(timeout=timeout, return_adv=True,
                                        service_uuids=[SERVICE_UUID])
    return [(d, adv.rssi) for d, adv in found.values()]


class BleBadge:
    """Persistent BLE connection, so repeated uploads skip the scan/connect cost.

    Usage::

        async with BleBadge() as badge:
            await badge.send(payload)
    """

    def __init__(self, name: str = DEFAULT_NAME, address: str | None = None,
                 timeout: float = 10.0) -> None:
        self.name, self.address, self.timeout = name, address, timeout
        self.client: BleakClient | None = None

    async def connect(self) -> None:
        """Find the badge (by address, else by name) and connect."""
        if self.address:
            dev = await BleakScanner.find_device_by_address(self.address, timeout=self.timeout)
        else:
            dev = await BleakScanner.find_device_by_name(self.name, timeout=self.timeout)
        if dev is None:
            raise BadgeNotFound(f"no BLE badge '{self.address or self.name}' found - is it on and "
                                "unplugged, with Bluetooth enabled on the badge?")
        self.address = dev.address
        self.client = BleakClient(dev, timeout=self.timeout)
        await self.client.connect()

    @property
    def connected(self) -> bool:
        return self.client is not None and self.client.is_connected

    async def send(self, payload: bytes) -> float:
        """Upload a payload, reconnecting if needed. Returns seconds taken."""
        if not self.connected:
            await self.connect()
        assert self.client is not None
        need = required_bytes(payload)
        t0 = time.perf_counter()
        for i in range(0, len(payload), CHUNK):
            try:
                await self.client.write_gatt_char(CHAR_UUID, payload[i:i + CHUNK], response=True)
            except BleakError:
                # the badge hangs up once it has everything it needs
                if i >= need:
                    break
                raise
        return time.perf_counter() - t0

    async def close(self) -> None:
        if self.client is not None:
            try:
                await self.client.disconnect()
            except BleakError:
                pass
            self.client = None

    async def __aenter__(self) -> "BleBadge":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()


def send(payload: bytes, name: str = DEFAULT_NAME, address: str | None = None) -> float:
    """One-shot synchronous upload over BLE (connect, write, disconnect)."""
    async def run() -> float:
        async with BleBadge(name, address) as badge:
            return await badge.send(payload)
    return asyncio.run(run())
