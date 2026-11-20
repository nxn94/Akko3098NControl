"""3098N settings protocol, verified on USB 320f:506a.

Wire format: ID 04, unsigned LE checksum of wire[3:64], command, length,
LE byte offset, response status, data. Transport adds the ID; all indices
below therefore refer to the 63-byte payload (wire offset minus one).

Unlike generic EVision V1, opcode 06 writes a settings block. The active
lighting record is 21 bytes at offset zero. BEGIN/END are rejected by this
firmware and are never sent. See docs/usb-protocol.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from .device import Akko3098N
from .hid_desc import VENDOR_PAYLOAD_LEN


class Cmd(IntEnum):
    READ_SETTINGS = 0x05
    WRITE_SETTINGS = 0x06
    DEVICE_INFO = 0x03
    FACTORY_KEYMAP = 0x07
    READ_KEYMAP = 0x08
    WRITE_KEYMAP = 0x09
    READ_COLORS = 0x0A
    WRITE_COLORS = 0x0B
    READ_MACROS = 0x14
    WRITE_MACROS = 0x15
    LED_MAP = 0x1B


class Mode(IntEnum):
    """Values from the vendor mode list; static and wave verified live."""

    STATIC = 1
    STEP = 2
    BREATHING = 3
    REACTIVE = 4
    STONE = 5
    TRAVERSE = 6
    SCAN = 7
    VORTEX = 8
    SPEED = 9
    STARS = 10
    WAVE_VERTICAL = 11
    ROLL = 12
    METEOR = 13
    RIPPLE = 14
    TRIGGER_OFF = 15
    CELL = 16
    RAIN = 17
    WAVE = 18
    MIX_COLOR = 19
    OFF = 20
    CUSTOM = 21


class Brightness(IntEnum):
    OFF = 0
    LOWEST = 1
    LOW = 2
    HIGH = 3
    HIGHEST = 4


class Speed(IntEnum):
    LEVEL_0 = 0
    LEVEL_1 = 1
    NORMAL = 2
    LEVEL_3 = 3
    LEVEL_4 = 4


class PollingRate(IntEnum):
    # Keyboard dropdown/wire values; the mouse variant uses the reverse order.
    HZ_1000 = 0
    HZ_500 = 1
    HZ_250 = 2
    HZ_125 = 3


MAX_PACKET_SIZE = 24
LIGHTING_RECORD_SIZE = 21


class ProtocolError(RuntimeError):
    """Transport succeeded but the device did not confirm the command."""


def _checksum(buf: bytearray) -> None:
    """Checksum payload[2:] (wire[3:]); store LE at payload[0:2]."""
    buf[0:2] = (sum(buf[2:]) & 0xFFFF).to_bytes(2, "little")


def _packet(opcode: int) -> bytearray:
    buf = bytearray(VENDOR_PAYLOAD_LEN)
    buf[2] = opcode
    return buf


def _send(dev: Akko3098N, buf: bytearray) -> bytes:
    """Send once, match the reply header, and inspect status; never retry writes.

    Reply checksum echoes the *request* checksum even when data changes. It
    must not be recomputed over read responses. Wire byte 7 is response status.
    """
    if len(buf) != VENDOR_PAYLOAD_LEN:
        raise ValueError("expected a 63-byte payload")
    _checksum(buf)
    count = dev.send_report(bytes(buf))
    if count != 64:
        raise ProtocolError(f"Short HID write: {count}/64 bytes")
    reply = dev.recv_report(timeout_ms=1000)
    if reply is None:
        raise ProtocolError(f"No reply to command 0x{buf[2]:02x}; check USB wired mode")
    if len(reply) != VENDOR_PAYLOAD_LEN or reply[:6] != bytes(buf[:6]):
        raise ProtocolError(f"Unexpected reply to command 0x{buf[2]:02x}: {reply.hex()}")
    if reply[6] != 0:
        raise ProtocolError(f"Keyboard rejected command 0x{buf[2]:02x} (status 0x{reply[6]:02x})")
    return reply


def read_settings(dev: Akko3098N, offset: int = 0, size: int = LIGHTING_RECORD_SIZE) -> bytes:
    """Read at most 24 bytes per packet; expose only the inspected 256-byte area."""
    if not 0 <= offset < 256 or not 1 <= size <= 256 - offset:
        raise ValueError("settings read must be within the first 256 bytes")
    result = bytearray()
    for current in range(offset, offset + size, MAX_PACKET_SIZE):
        count = min(MAX_PACKET_SIZE, offset + size - current)
        packet = _packet(Cmd.READ_SETTINGS)
        packet[3] = count
        packet[4:6] = current.to_bytes(2, "little")
        result.extend(_send(dev, packet)[7:7 + count])
    return bytes(result)


def write_lighting(dev: Akko3098N, record: bytes) -> None:
    """Write only the verified 21-byte lighting record, then verify by readback.

    No automatic retry or rollback: a timeout may mean the write was applied.
    Preserve reserved bytes with a read/modify/write in the feature layer.
    """
    if len(record) != LIGHTING_RECORD_SIZE:
        raise ValueError("lighting record must be exactly 21 bytes")
    packet = _packet(Cmd.WRITE_SETTINGS)
    packet[3] = LIGHTING_RECORD_SIZE
    packet[7:7 + LIGHTING_RECORD_SIZE] = record
    _send(dev, packet)
    if read_settings(dev) != record:
        raise ProtocolError("Lighting readback differs from the requested settings; write not confirmed")


def set_parameter(dev: Akko3098N, param: int, data: bytes) -> bytes:
    """Block the obsolete generic parameter API: its offsets are not 3098N IDs."""
    raise ProtocolError("Generic EVision parameter writes are unsupported on the 3098N")


__all__ = [
    "LIGHTING_RECORD_SIZE", "MAX_PACKET_SIZE", "Brightness", "Cmd", "Mode",
    "PollingRate", "ProtocolError", "Speed", "read_settings", "write_lighting",
    "DeviceInfo", "device_info", "read_keymap", "read_colors", "read_led_map",
    "read_macros", "write_keymap", "write_colors", "write_settings_field", "write_macros",
]


@dataclass(frozen=True)
class DeviceInfo:
    slots: int
    macro_capacity: int
    raw: bytes


def _read_region(dev: Akko3098N, command: Cmd, offset: int, size: int) -> bytes:
    if command not in (Cmd.DEVICE_INFO, Cmd.READ_SETTINGS, Cmd.FACTORY_KEYMAP,
                       Cmd.READ_KEYMAP, Cmd.READ_COLORS, Cmd.READ_MACROS, Cmd.LED_MAP):
        raise ValueError("not a read command")
    if not 0 <= offset < 65536 or not 1 <= size <= 65536 - offset:
        raise ValueError("invalid region")
    result = bytearray()
    for current in range(offset, offset + size, MAX_PACKET_SIZE):
        count = min(MAX_PACKET_SIZE, offset + size - current)
        packet = _packet(command)
        packet[3] = count
        packet[4:6] = current.to_bytes(2, "little")
        result.extend(_send(dev, packet)[7:7 + count])
    return bytes(result)


def device_info(dev: Akko3098N) -> DeviceInfo:
    raw = _read_region(dev, Cmd.DEVICE_INFO, 0, 34)
    # Vendor 0045a0e1: byte 5 is matrix slots, byte 6 macro size / 128.
    if raw[:2] != b"\xaa\x55" or not 1 <= raw[5] <= 170 or not 1 <= raw[6] <= 64:
        raise ProtocolError("Unsupported device information layout")
    return DeviceInfo(raw[5], raw[6] * 128, raw)


def read_keymap(dev: Akko3098N, *, factory: bool = False) -> bytes:
    count = device_info(dev).slots
    return _read_region(dev, Cmd.FACTORY_KEYMAP if factory else Cmd.READ_KEYMAP, 0, count * 3)


def read_colors(dev: Akko3098N) -> bytes:
    return _read_region(dev, Cmd.READ_COLORS, 0, device_info(dev).slots * 3)


def read_led_map(dev: Akko3098N) -> bytes:
    return _read_region(dev, Cmd.LED_MAP, 0, device_info(dev).slots)


def read_macros(dev: Akko3098N) -> bytes:
    return _read_region(dev, Cmd.READ_MACROS, 0, device_info(dev).macro_capacity)


def _write_region(dev: Akko3098N, command: Cmd, offset: int, data: bytes) -> None:
    readers = {Cmd.WRITE_SETTINGS: Cmd.READ_SETTINGS, Cmd.WRITE_KEYMAP: Cmd.READ_KEYMAP,
               Cmd.WRITE_COLORS: Cmd.READ_COLORS, Cmd.WRITE_MACROS: Cmd.READ_MACROS}
    if command not in readers:
        raise ValueError("not a settings write command")
    if not data or offset < 0 or offset + len(data) > 65536:
        raise ValueError("invalid write region")
    for current in range(0, len(data), MAX_PACKET_SIZE):
        chunk = data[current:current + MAX_PACKET_SIZE]
        packet = _packet(command)
        packet[3] = len(chunk)
        packet[4:6] = (offset + current).to_bytes(2, "little")
        packet[7:7 + len(chunk)] = chunk
        _send(dev, packet)
    if _read_region(dev, readers[command], offset, len(data)) != data:
        raise ProtocolError(f"Readback mismatch for command 0x{command:02x}; restore the saved backup")


def write_keymap(dev: Akko3098N, data: bytes, offset: int = 0) -> None:
    size = device_info(dev).slots * 3
    if offset % 3 or len(data) % 3 or offset < 0 or offset + len(data) > size:
        raise ValueError("keymap must contain complete triples within the matrix")
    _write_region(dev, Cmd.WRITE_KEYMAP, offset, data)


def write_colors(dev: Akko3098N, data: bytes) -> None:
    if len(data) != device_info(dev).slots * 3:
        raise ValueError("incorrect color matrix length")
    _write_region(dev, Cmd.WRITE_COLORS, 0, data)


def write_settings_field(dev: Akko3098N, offset: int, data: bytes) -> None:
    # Only Windows-key enable (21) and polling selector (22) are verified here.
    allowed = {21: (0, 1), 22: (0, 1, 2, 3)}
    if offset not in allowed or len(data) != 1 or data[0] not in allowed[offset]:
        raise ValueError("unverified system field")
    _write_region(dev, Cmd.WRITE_SETTINGS, offset, data)


def write_macros(dev: Akko3098N, data: bytes) -> None:
    """Replace the bounded USB macro bank and verify all bytes.

    Firmware 0x2d25e skips the first 16 bytes when deciding whether an offset-0
    chunk changed. A header-only change therefore needs an offset-1 write after
    the ordinary upload. Byte 0 (magic) changes with the first record offset on
    transitions between empty and populated banks. No transfer session/retry.
    """
    if len(data) != device_info(dev).macro_capacity:
        raise ValueError('incorrect macro bank length')
    for offset in range(0, len(data), MAX_PACKET_SIZE):
        chunk = data[offset:offset + MAX_PACKET_SIZE]
        packet = _packet(Cmd.WRITE_MACROS)
        packet[3] = len(chunk)
        packet[4:6] = offset.to_bytes(2, 'little')
        packet[7:7 + len(chunk)] = chunk
        _send(dev, packet)
    if _read_region(dev, Cmd.READ_MACROS, 1, 15) != data[1:16]:
        _write_region(dev, Cmd.WRITE_MACROS, 1, data[1:16])
    if read_macros(dev) != data:
        raise ProtocolError('Macro bank readback mismatch; restore the saved backup')
