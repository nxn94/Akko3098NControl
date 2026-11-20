"""Verified onboard keyboard macros, independent of archived ShootData files.

Wire events: LE16 delay, 0x8a press / 0x0a release, USB HID usage. Type 10
uses the firmware's rollover handler. Type 9 takes a modifier mask and type 1
takes a mouse button mask. Bit 7 marks a press for each of these types.
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass

from ..protocol import device_info, read_keymap, read_macros, write_keymap, write_macros
from .live_keymap import Assignment, parse_target

FORMAT = 'akko-3098n-usb-macros-v1'
MAX_EVENTS = 512
_MOUSE = {'mouse:left': 1, 'mouse:right': 2, 'mouse:middle': 4,
          'mouse:back': 8, 'mouse:forward': 16}


@dataclass(frozen=True)
class Event:
    usage: int | None
    pressed: bool
    delay_ms: int = 100
    mouse: bool = False


def validate_events(events: list[Event]) -> None:
    if len(events) > MAX_EVENTS:
        raise ValueError(f'macro exceeds {MAX_EVENTS} events')
    held = set()
    duration = 0
    for event in events:
        if type(event.pressed) is not bool:
            raise ValueError('macro pressed must be boolean')
        if type(event.delay_ms) is not int or not 1 <= event.delay_ms <= 10000:
            raise ValueError('macro delay must be 1..10000 ms')
        duration += event.delay_ms
        if type(event.mouse) is not bool:
            raise ValueError('macro mouse flag must be boolean')
        if event.usage is None:
            if event.pressed or event.mouse:
                raise ValueError('wait events cannot press keys or mouse buttons')
            continue
        if type(event.usage) is not int:
            raise ValueError('macro usage must be an integer')
        if event.mouse:
            if event.usage not in _MOUSE.values():
                raise ValueError('invalid mouse button mask')
        elif not (4 <= event.usage <= 0x93 or 0xe0 <= event.usage <= 0xe7):
            raise ValueError('macro key must be a rollover usage or modifier')
        target = (event.mouse, event.usage)
        if event.pressed:
            if target in held:
                raise ValueError('macro presses an already-held key or button')
            held.add(target)
        else:
            if target not in held:
                raise ValueError('macro releases a key or button that is not held')
            held.remove(target)
    if held:
        raise ValueError('macro must release every pressed key')
    if duration > 60000:
        raise ValueError('macro exceeds 60 seconds')


def _targets(name: str) -> list[tuple[int, bool]]:
    if name in _MOUSE:
        return [(_MOUSE[name], True)]
    target = parse_target(name)
    if target.kind != 0x20 or not (target.usage or target.modifiers):
        raise ValueError('macro needs a keyboard key, chord, or mouse button')
    result = [(0xe0 + bit, False) for bit in range(8) if target.modifiers & (1 << bit)]
    if target.usage:
        result.append((target.usage, False))
    return result


def sequence(keys: list[str], delay_ms: int = 100, repeat: int = 1) -> list[Event]:
    if not keys:
        raise ValueError('macro needs at least one key or mouse button')
    if type(repeat) is not int or not 1 <= repeat <= MAX_EVENTS // 2:
        raise ValueError('invalid macro repeat count')
    steps = []
    for key in keys:
        targets = _targets(key)
        steps.extend(Event(code, True, delay_ms, mouse) for code, mouse in targets)
        steps.extend(Event(code, False, delay_ms, mouse) for code, mouse in reversed(targets))
    # Firmware applies each delay after the event. Preserve the initial wait.
    result = [Event(None, False, 100)] + steps * repeat
    validate_events(result)
    return result


def _encode_event(event: Event) -> bytes:
    code = event.usage
    if code is None:
        kind, code = 0, 0
    elif event.mouse:
        kind = 1
    elif code >= 0xe0:
        kind, code = 9, 1 << (code - 0xe0)
    else:
        kind = 10
    return struct.pack('<HBB', event.delay_ms, kind | (0x80 if event.pressed else 0), code)


def encode(bank: list[list[Event]], capacity: int) -> bytes:
    if len(bank) > 256:
        raise ValueError('macro indices must fit one byte')
    for events in bank:
        validate_events(events)
    if not bank:
        return bytes(capacity)
    offset = 16 + 2 * len(bank)
    records = bytearray()
    offsets = bytearray()
    for events in bank:
        if offset + 4 + 4 * len(events) > capacity:
            raise ValueError(f'macro bank exceeds device capacity of {capacity} bytes')
        offsets += struct.pack('<H', offset)
        record = struct.pack('<HH', len(events), 0)
        record += b''.join(_encode_event(event) for event in events)
        records += record
        offset += len(record)
    if offset > capacity:
        raise ValueError(f'macro bank needs {offset} bytes; device has {capacity}')
    header = struct.pack('<HHH', 0x55aa, offset, len(bank)) + bytes(10)
    return (header + offsets + records).ljust(capacity, b'\0')


def decode(raw: bytes) -> list[list[Event]]:
    if not any(raw):
        return []
    if len(raw) < 16:
        raise ValueError('truncated macro header')
    magic, total, count = struct.unpack_from('<HHH', raw)
    if magic != 0x55aa or not 1 <= count <= 256 or not 16 + 2 * count <= total <= len(raw):
        raise ValueError('unsupported macro header')
    if any(raw[6:16]) or any(raw[total:]):
        raise ValueError('unknown macro header or trailing data; refusing to discard it')
    expected = 16 + 2 * count
    result = []
    for index in range(count):
        offset = struct.unpack_from('<H', raw, 16 + 2 * index)[0]
        if offset != expected or offset + 4 > total:
            raise ValueError('invalid macro record offset')
        size, reserved = struct.unpack_from('<HH', raw, offset)
        end = offset + 4 + 4 * size
        if reserved or end > total or size > MAX_EVENTS:
            raise ValueError('invalid macro record length or reserved data')
        events = []
        for position in range(offset + 4, end, 4):
            delay, wire_kind, usage = struct.unpack_from('<HBB', raw, position)
            pressed = bool(wire_kind & 0x80)
            kind = wire_kind & 0x7f
            if wire_kind == 0 and usage == 0:
                events.append(Event(None, False, delay))
            elif kind == 1 and usage in _MOUSE.values():
                events.append(Event(usage, pressed, delay, mouse=True))
            elif kind == 9 and usage and usage.bit_count() == 1:
                events.append(Event(0xe0 + usage.bit_length() - 1, pressed, delay))
            elif kind == 10 and 4 <= usage <= 0x93:
                events.append(Event(usage, pressed, delay))
            else:
                raise ValueError(f'unsupported macro event 0x{wire_kind:02x}/0x{usage:02x}')
        validate_events(events)
        result.append(events)
        expected = end
    if expected != total:
        raise ValueError('macro total length does not match records')
    return result


def _export_event(event: Event) -> dict:
    if event.usage is None:
        return {'action': 'wait', 'delay_ms': event.delay_ms}
    if event.mouse:
        name = next(name for name, mask in _MOUSE.items() if mask == event.usage)
    elif event.usage >= 0xe0:
        name = Assignment(0x20, 1 << (event.usage - 0xe0), 0).describe()
    else:
        name = Assignment(0x20, 0, event.usage).describe()
    return {'key': name, 'action': 'down' if event.pressed else 'up', 'delay_ms': event.delay_ms}


def export(bank: list[list[Event]]) -> dict:
    return {'format': FORMAT, 'macros': [{'events': [_export_event(event) for event in events]}
                                        for events in bank]}


def parse(data: dict) -> list[list[Event]]:
    if not isinstance(data, dict) or data.get('format') != FORMAT or not isinstance(data.get('macros'), list):
        raise ValueError('not an Akko onboard macro JSON file')
    bank = []
    for macro in data['macros']:
        if not isinstance(macro, dict) or not isinstance(macro.get('events'), list):
            raise ValueError('macro events must be a list')
        events = []
        for event in macro['events']:
            if isinstance(event, dict) and event.get('action') == 'wait':
                events.append(Event(None, False, event.get('delay_ms')))
                continue
            if not isinstance(event, dict) or not isinstance(event.get('key'), str):
                raise ValueError('macro event needs a key name')
            targets = _targets(event['key'])
            if len(targets) != 1 or event.get('action') not in ('down', 'up'):
                raise ValueError('each macro event needs one key or mouse button and a down/up action')
            code, mouse = targets[0]
            events.append(Event(code, event['action'] == 'down', event.get('delay_ms'), mouse))
        validate_events(events)
        bank.append(events)
    return bank


def validate_bindings(keymap: bytes, bank: list[list[Event]]) -> None:
    for offset in range(0, len(keymap), 3):
        kind, index, mode = keymap[offset:offset + 3]
        if kind in (0x70, 0x71):
            if index >= len(bank) or not bank[index]:
                raise ValueError(f'slot {offset // 3} refers to missing/empty macro {index}; rebind it first')
            if kind != 0x70 or mode != 0:
                raise ValueError('only verified one-shot macro bindings are supported')


def upload(dev, bank: list[list[Event]]) -> None:
    for events in bank:
        if events and (events[0].usage is not None or events[0].delay_ms < 100):
            raise ValueError('macro must begin with a wait event of at least 100 ms')
    raw = encode(bank, device_info(dev).macro_capacity)
    active = read_keymap(dev)
    validate_bindings(active, bank)
    current = read_macros(dev)
    if current != raw:
        suspend_bindings(dev, active, decode(current))
        write_macros(dev, raw)
        for offset in range(0, len(active), 3):
            if active[offset] in (0x70, 0x71):
                write_keymap(dev, active[offset:offset + 3], offset)


def bind(dev, slot: int, index: int) -> None:
    factory = read_keymap(dev, factory=True)
    if not 0 <= slot < len(factory) // 3 or factory[3 * slot] != 0x20:
        raise ValueError('slot is empty or a protected special function key')
    bank = decode(read_macros(dev))
    if not 0 <= index < len(bank) or not bank[index]:
        raise ValueError('macro index is missing or empty')
    write_keymap(dev, bytes([0x70, index, 0]), slot * 3)



def suspend_bindings(dev, keymap: bytes, bank: list[list[Event]] | None = None) -> None:
    """Disable macro triggers while replacing their shared table; never grab input."""
    if bank is None:
        bank = decode(read_macros(dev))
    validate_bindings(keymap, bank)
    for offset in range(0, len(keymap), 3):
        if keymap[offset] in (0x70, 0x71):
            write_keymap(dev, bytes.fromhex('200000'), offset)
    # A macro already started before suspension can still be running. Wait its
    # bounded maximum duration before modifying shared playback memory.
    duration = max((sum(e.delay_ms for e in events) for events in bank), default=0)
    if duration:
        if duration > 1000:
            print(f'Waiting up to {duration / 1000:g}s for prior macro playback to finish', flush=True)
        time.sleep(duration / 1000 + 0.05)
