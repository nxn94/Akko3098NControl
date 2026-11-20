"""Read/modify/write the active 3098N lighting record, preserving other fields."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..device import Akko3098N
from ..protocol import (
    Brightness,
    Mode,
    PollingRate,
    Speed,
    read_colors,
    read_keymap,
    read_led_map,
    read_settings,
    write_colors,
    write_lighting,
)


@dataclass
class ColorRGB:
    r: int
    g: int
    b: int

    def __post_init__(self) -> None:
        if any(type(c) is not int or not 0 <= c <= 255 for c in (self.r, self.g, self.b)):
            raise ValueError("RGB components must be integers in 0..255")

    def to_bytes(self) -> bytes:
        return bytes([self.r, self.g, self.b])

    @classmethod
    def from_hex(cls, hex_str: str) -> ColorRGB:
        s = hex_str.removeprefix("#")
        if len(s) != 6:
            raise ValueError(f"expected #RRGGBB, got {hex_str!r}")
        return cls(int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))

    def to_hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"


@dataclass
class LightingConfig:
    mode: Mode = Mode.STATIC
    brightness: Brightness = Brightness.HIGHEST
    speed: Speed = Speed.NORMAL
    random_flag: bool = False
    color: ColorRGB = field(default_factory=lambda: ColorRGB(255, 255, 255))

    def __post_init__(self) -> None:
        self.mode = Mode(self.mode)
        self.brightness = Brightness(self.brightness)
        self.speed = Speed(self.speed)
        if type(self.random_flag) is not bool:
            raise ValueError("random_flag must be true or false")


def decode(record: bytes) -> LightingConfig:
    if len(record) != 21:
        raise ValueError("expected a 21-byte lighting record")
    # Active record fields: +1 mode, +2 brightness, +3 inverted speed,
    # +5 multicolor flag, +6..8 RGB. +0, +4, +9..20 are preserved.
    return LightingConfig(
        mode=Mode(record[1]), brightness=Brightness(record[2]),
        speed=Speed(4 - record[3]), random_flag=bool(record[5]),
        color=ColorRGB(*record[6:9]),
    )


def encode(cfg: LightingConfig, original: bytes) -> bytes:
    # Revalidate mutable configuration objects before any device write.
    cfg.__post_init__()
    if len(original) != 21:
        raise ValueError("expected a 21-byte lighting record")
    record = bytearray(original)
    record[1] = int(cfg.mode)
    record[2] = int(cfg.brightness)
    record[3] = 4 - int(cfg.speed)
    record[5] = int(cfg.random_flag)
    record[6:9] = cfg.color.to_bytes()
    return bytes(record)


def get_config(dev: Akko3098N) -> LightingConfig:
    return decode(read_settings(dev))


def apply(dev: Akko3098N, cfg: LightingConfig) -> None:
    original = read_settings(dev)
    updated = encode(cfg, original)
    if updated != original:
        write_lighting(dev, updated)


def set_mode(dev: Akko3098N, mode: Mode) -> None:
    original = read_settings(dev)
    updated = bytearray(original)
    updated[1] = Mode(mode)
    if updated != original:
        write_lighting(dev, bytes(updated))


def set_brightness(dev: Akko3098N, brightness: int) -> None:
    brightness = Brightness(brightness)
    original = read_settings(dev)
    updated = bytearray(original)
    updated[2] = brightness
    if updated != original:
        write_lighting(dev, bytes(updated))


def set_static_color(dev: Akko3098N, color: ColorRGB) -> None:
    apply(dev, LightingConfig(mode=Mode.STATIC, color=color))


def set_per_key(dev: Akko3098N, colors: list[ColorRGB]) -> None:
    """Colors in firmware LED order; require the complete device-sized matrix."""
    original = read_colors(dev)
    payload = b"".join(color.to_bytes() for color in colors)
    if len(payload) != len(original):
        raise ValueError(f"expected {len(original) // 3} RGB triples")
    if original != payload:
        write_colors(dev, payload)
    set_mode(dev, Mode.CUSTOM)


def set_key_color(dev: Akko3098N, slot: int, color: ColorRGB) -> None:
    set_key_colors(dev, (slot,), color)


def set_key_colors(dev: Akko3098N, slots: tuple[int, ...], color: ColorRGB) -> None:
    if not slots:
        return
    mapping = read_led_map(dev)
    factory = read_keymap(dev, factory=True)
    original = read_colors(dev)
    updated = bytearray(original)
    rgb = color.to_bytes()
    for slot in slots:
        if (not 0 <= slot < len(mapping) or mapping[slot] == 0xff
                or factory[slot * 3:slot * 3 + 3] == bytes(3)):
            raise ValueError(f"slot has no addressable LED (slot {slot})")
        offset = mapping[slot] * 3
        if offset + 3 > len(original):
            raise ValueError("invalid LED mapping returned by keyboard")
        updated[offset:offset + 3] = rgb
    settings = read_settings(dev)
    custom = bytearray(settings)
    custom[1] = Mode.CUSTOM
    mode_attempted = False
    try:
        if updated != original:
            write_colors(dev, bytes(updated))
        if custom != settings:
            mode_attempted = True
            write_lighting(dev, bytes(custom))
    except (OSError, RuntimeError):
        try:
            if updated != original:
                write_colors(dev, original)
            if mode_attempted:
                write_lighting(dev, settings)
        except (OSError, RuntimeError) as exc:
            raise RuntimeError('Could not roll back the color edit. Restore the saved profile.') from exc
        raise


__all__ = [
    "Brightness", "ColorRGB", "LightingConfig", "Mode", "PollingRate", "Speed",
    "apply", "decode", "encode", "get_config", "set_brightness", "set_mode",
    "set_key_color", "set_key_colors", "set_per_key", "set_static_color",
]
