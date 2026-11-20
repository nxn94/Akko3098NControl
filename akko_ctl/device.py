"""Linux hidraw transport, restricted to the 3098N vendor report.

The kernel retains ownership of keyboard input. Opening hidraw does not detach
its driver or grab evdev. A nonblocking advisory lock serializes tool instances.
"""

from __future__ import annotations

import fcntl
import os
import select
import time
from pathlib import Path
from typing import Self

from .hid_desc import (
    PID,
    VENDOR_PAYLOAD_LEN,
    VENDOR_REPORT_ID,
    VENDOR_REPORT_LEN,
    VENDOR_USAGE,
    VENDOR_USAGE_PAGE,
    VID,
)

_SYS_HIDRAW = Path("/sys/class/hidraw")
# Vendor Application collection, report 4, 8-bit fields, 63 output bytes.
_VENDOR_DESCRIPTOR = bytes.fromhex(
    "06 1c ff 09 92 a1 01 85 04 19 00 2a ff 00 15 00 26 ff 00 75 08 95 3f 91 00"
)


class Akko3098N:
    """One verified Linux vendor interface, with exclusive application access."""

    def __init__(self, hidraw_path: str | bytes):
        self.path = os.fsdecode(hidraw_path)
        matches = [i for i in self.find() if i["path"] == self.path
                   and i["usage_page"] == VENDOR_USAGE_PAGE]
        if not matches:
            raise RuntimeError(f"Not a verified Akko 3098N vendor interface: {self.path}")
        self._info = matches[0]
        self._fd = os.open(self.path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            os.close(self._fd)
            self._fd = None
            raise RuntimeError("Keyboard is already in use by another akko-ctl process") from exc

    @classmethod
    def find(cls) -> list[dict]:
        """Enumerate sysfs metadata without opening devices or sending USB traffic."""
        infos = []
        for node in sorted(_SYS_HIDRAW.glob("hidraw*")):
            try:
                dev = node / "device"
                meta = dict(line.split("=", 1) for line in
                            (dev / "uevent").read_text().splitlines() if "=" in line)
                bus, vendor, product = (int(v, 16) for v in meta["HID_ID"].split(":"))
                if (bus, vendor, product) != (3, VID, PID):
                    continue
                descriptor = (dev / "report_descriptor").read_bytes()
                usb = dev.resolve().parent
                is_vendor = _VENDOR_DESCRIPTOR in descriptor
                infos.append({
                    "path": f"/dev/{node.name}", "vendor_id": vendor, "product_id": product,
                    "interface_number": int((usb / "bInterfaceNumber").read_text(), 16),
                    "usage_page": VENDOR_USAGE_PAGE if is_vendor else 1,
                    "usage": VENDOR_USAGE if is_vendor else 6,
                    "manufacturer_string": (usb.parent / "manufacturer").read_text().strip(),
                    "product_string": (usb.parent / "product").read_text().strip(),
                    "serial_number": meta.get("HID_UNIQ", ""),
                })
            except (OSError, KeyError, ValueError):
                continue
        return infos

    @classmethod
    def open_vendor(cls) -> Akko3098N:
        for info in cls.find():
            if info["usage_page"] == VENDOR_USAGE_PAGE and info["usage"] == VENDOR_USAGE:
                try:
                    return cls(info["path"])
                except PermissionError as exc:
                    raise PermissionError(
                        f"No read/write access to {info['path']}. Install the supplied udev rule "
                        "and reconnect the keyboard (see README)."
                    ) from exc
        raise RuntimeError("Akko 3098N USB vendor interface not found; connect in wired mode.")

    @property
    def manufacturer(self) -> str:
        return self._info["manufacturer_string"]

    @property
    def product(self) -> str:
        return self._info["product_string"]

    @property
    def serial(self) -> str:
        return self._info["serial_number"]

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _with_report_id(self, payload: bytes) -> bytes:
        if len(payload) > VENDOR_PAYLOAD_LEN:
            raise ValueError(f"vendor payload exceeds {VENDOR_PAYLOAD_LEN} bytes")
        return bytes([VENDOR_REPORT_ID]) + payload.ljust(VENDOR_PAYLOAD_LEN, b"\x00")

    def send_report(self, payload: bytes) -> int:
        """Prepend exactly one ID; a short write is an error, never success."""
        report = self._with_report_id(payload)
        count = os.write(self._fd, report)
        if count != VENDOR_REPORT_LEN:
            raise OSError(f"Short HID write: {count}/{VENDOR_REPORT_LEN} bytes")
        return count

    def recv_report(self, timeout_ms: int = 500) -> bytes | None:
        """Wait to the deadline, ignoring keyboard/media input on this interface."""
        if timeout_ms < 0:
            raise ValueError("timeout must be nonnegative")
        deadline = time.monotonic() + timeout_ms / 1000
        while True:
            remaining = max(0, deadline - time.monotonic())
            if not select.select([self._fd], [], [], remaining)[0]:
                return None
            try:
                data = os.read(self._fd, VENDOR_REPORT_LEN)
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    return None
                continue
            if not data:
                raise OSError("Keyboard disconnected")
            if data[0] == VENDOR_REPORT_ID:
                if len(data) != VENDOR_REPORT_LEN:
                    raise OSError(f"Short vendor reply: {len(data)} bytes")
                return data[1:]
            if time.monotonic() >= deadline:
                return None


__all__ = ["Akko3098N"]
