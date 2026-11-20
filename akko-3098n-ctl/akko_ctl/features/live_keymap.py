"""Live 3098N matrix assignments, separate from legacy vendor JSON utilities."""

from __future__ import annotations

from dataclasses import dataclass

from ..device import Akko3098N
from ..protocol import read_keymap, write_keymap

# USB HID usages, not Linux evdev codes or vendor JSON indices.
_NAMES = {chr(97 + i): 4 + i for i in range(26)}
_NAMES.update({str(i + 1): 0x1e + i for i in range(9)})
_NAMES.update({'0': 0x27, 'enter': 0x28, 'escape': 0x29, 'backspace': 0x2a,
               'tab': 0x2b, 'space': 0x2c, 'caps-lock': 0x39, 'delete': 0x4c,
               'right': 0x4f, 'left': 0x50, 'down': 0x51, 'up': 0x52,
               'num-lock': 0x53, 'kp-1': 0x59, 'kp-2': 0x5a, 'kp-3': 0x5b,
               'kp-4': 0x5c, 'kp-5': 0x5d, 'kp-6': 0x5e, 'kp-7': 0x5f,
               'kp-8': 0x60, 'kp-9': 0x61, 'kp-0': 0x62, 'kp-dot': 0x63})
_NAMES.update({f'f{i + 1}': 0x3a + i for i in range(12)})
_MODIFIERS = {'left-ctrl': 1, 'left-shift': 2, 'left-alt': 4, 'left-win': 8,
              'right-ctrl': 16, 'right-shift': 32, 'right-alt': 64, 'right-win': 128}


# Consumer-page usages in little-endian order on the wire (firmware 0x2c6b8).
_MEDIA = {
    'media:play-pause': 0xcd, 'media:next': 0xb5, 'media:previous': 0xb6,
    'media:stop': 0xb7, 'media:mute': 0xe2, 'media:volume-up': 0xe9,
    'media:volume-down': 0xea,
}


@dataclass(frozen=True)
class Assignment:
    kind: int
    modifiers: int
    usage: int

    def to_bytes(self) -> bytes:
        return bytes((self.kind, self.modifiers, self.usage))

    @classmethod
    def from_bytes(cls, value: bytes) -> Assignment:
        if len(value) != 3:
            raise ValueError('assignment must be three bytes')
        return cls(*value)

    def describe(self) -> str:
        if self.kind == 0x20:
            parts = [name for name, mask in _MODIFIERS.items() if self.modifiers & mask]
            if self.usage:
                parts.append(next((n for n, code in _NAMES.items() if code == self.usage), f'hid:0x{self.usage:02x}'))
            return '+'.join(parts) or 'none'
        if self.kind == 0x30:
            code = self.modifiers | self.usage << 8
            return next((name for name, usage in _MEDIA.items() if usage == code),
                        f'raw:{self.to_bytes().hex()}')
        return f'raw:{self.to_bytes().hex()}'


def parse_target(value: str) -> Assignment:
    """Parse ordinary keys, modifier chords, or named media keys."""
    value = value.lower()
    if value in _MEDIA:
        return Assignment(0x30, _MEDIA[value], 0)
    if value == 'none':
        return Assignment(0x20, 0, 0)
    mods = 0
    usage = 0
    for part in value.split('+'):
        if part in _MODIFIERS:
            mods |= _MODIFIERS[part]
        else:
            if usage:
                raise ValueError('a chord may contain only one ordinary key')
            code = _NAMES.get(part)
            if code is None:
                try:
                    code = int(part.removeprefix('hid:'), 0)
                except ValueError as exc:
                    raise ValueError(f'unknown key {part!r}') from exc
            if not 4 <= code <= 0xe7:
                raise ValueError('HID usage must be 0x04..0xe7')
            if 0xe0 <= code <= 0xe7:
                mods |= 1 << (code - 0xe0)
            else:
                usage = code
    return Assignment(0x20, mods, usage)


def describe(dev: Akko3098N) -> list[tuple[int, Assignment, Assignment]]:
    factory = read_keymap(dev, factory=True)
    active = read_keymap(dev)
    return [(i // 3, Assignment.from_bytes(factory[i:i + 3]), Assignment.from_bytes(active[i:i + 3]))
            for i in range(0, len(active), 3) if factory[i:i + 3] != bytes(3)]


def rebind(dev: Akko3098N, slot: int, target: Assignment) -> None:
    rebind_keys(dev, {slot: target})


def rebind_keys(dev: Akko3098N, targets: dict[int, Assignment | None]) -> None:
    """Apply remaps together. A None target restores that slot's factory value."""
    if not targets:
        return
    active = read_keymap(dev)
    factory = read_keymap(dev, factory=True)
    changes = []
    for slot, target in sorted(targets.items()):
        offset = slot * 3
        original = factory[offset:offset + 3]
        if not 0 <= slot < len(active) // 3 or not original or original == bytes(3):
            raise ValueError(f'slot {slot} is outside the populated matrix')
        if original[0] != 0x20:
            raise ValueError(f'special function slots cannot be rebound (slot {slot})')
        if target is not None and target.kind != 0x20 and target.describe() not in _MEDIA:
            raise ValueError('unsupported assignment type')
        before = active[offset:offset + 3]
        after = original if target is None else target.to_bytes()
        if before != after:
            changes.append((offset, before, after))

    for index, (offset, _, after) in enumerate(changes):
        try:
            write_keymap(dev, after, offset)
        except (OSError, RuntimeError):
            if len(changes) > 1:
                try:
                    for written_offset, before, _ in reversed(changes[:index + 1]):
                        write_keymap(dev, before, written_offset)
                except (OSError, RuntimeError) as exc:
                    raise RuntimeError('Could not roll back the batch remap. Restore the saved profile.') from exc
            raise
