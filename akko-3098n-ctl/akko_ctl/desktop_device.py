"""Structured device access for the desktop application."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from .device import Akko3098N
from .features import lighting, live_keymap, snapshot, usb_macros
from .protocol import PollingRate, device_info, read_keymap, read_led_map, read_macros


@dataclass(frozen=True)
class Key:
    slot: int
    factory: live_keymap.Assignment
    current: live_keymap.Assignment
    color: str | None

    @property
    def assignment(self) -> str:
        if self.current.kind == 0x70 and self.current.usage == 0:
            return f'Macro {self.current.modifiers + 1}'
        return self.current.describe()


@dataclass(frozen=True)
class State:
    path: str
    config: lighting.LightingConfig
    keys: list[Key]
    macros: list[list[usb_macros.Event]] | None
    macro_error: str
    windows_enabled: bool
    rate: PollingRate


def backup_directory() -> Path:
    base = Path(os.environ.get('XDG_STATE_HOME') or Path.home() / '.local/state')
    if not base.is_absolute():
        base = Path.home() / '.local/state'
    return base / 'akko-3098n-ctl' / 'backups'


def read_state() -> State:
    with Akko3098N.open_vendor() as dev:
        data = snapshot.capture(dev)
        factory = read_keymap(dev, factory=True)
        mapping = read_led_map(dev)
        path = dev.path
    active = bytes.fromhex(data['keymap'])
    colors = bytes.fromhex(data['colors'])
    keys = []
    for slot, led in enumerate(mapping):
        offset = slot * 3
        original = factory[offset:offset + 3]
        if original == bytes(3):
            continue
        color = '#' + colors[led * 3:led * 3 + 3].hex() if led < len(colors) // 3 else None
        keys.append(Key(slot, live_keymap.Assignment.from_bytes(original),
                        live_keymap.Assignment.from_bytes(active[offset:offset + 3]), color))
    macros, error = None, ''
    try:
        macros = usb_macros.decode(bytes.fromhex(data['macros']))
    except ValueError as exc:
        error = str(exc)
    return State(path, lighting.decode(bytes.fromhex(data['lighting'])), keys, macros,
                 error, data['windows_enabled'], PollingRate(data['polling_rate']))


def change_device(operation) -> Path:
    """Back up and change the same device under its existing advisory lock."""
    directory = backup_directory()
    with Akko3098N.open_vendor() as dev:
        directory.mkdir(parents=True, exist_ok=True)
        backup = snapshot.backup(dev, directory / f'{time.time_ns()}.akko.json')
        try:
            operation(dev)
        except (ValueError, OSError, RuntimeError) as exc:
            raise RuntimeError(f'{exc}\n\nBackup: {backup}') from exc
    return backup


def change_macro(dev: Akko3098N, index: int | None, events: list[usb_macros.Event]) -> None:
    bank = usb_macros.decode(read_macros(dev))
    if index is None:
        try:
            index = bank.index([])
        except ValueError:
            index = len(bank)
            bank.append([])
    if not 0 <= index < len(bank):
        raise ValueError('The macro slot no longer exists. Refresh the device.')
    bank[index] = events
    while bank and not bank[-1]:
        bank.pop()
    usb_macros.upload(dev, bank)


def save_profile(path: str) -> Path:
    with Akko3098N.open_vendor() as dev:
        return snapshot.save(snapshot.capture(dev), path)


def load_profile(dev: Akko3098N, path: str) -> None:
    snapshot.restore(dev, snapshot.load(path))


def fill_color(dev: Akko3098N, color: lighting.ColorRGB) -> None:
    lighting.set_per_key(dev, [color] * device_info(dev).slots)
