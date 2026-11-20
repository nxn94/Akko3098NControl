"""Versioned device snapshots, validated before any restore writes."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from ..device import Akko3098N
from ..protocol import (
    device_info,
    read_colors,
    read_keymap,
    read_macros,
    read_settings,
    write_colors,
    write_keymap,
    write_lighting,
    write_macros,
    write_settings_field,
)

FORMAT = 'akko-3098n-profile-v1'


def capture(dev: Akko3098N) -> dict:
    info = device_info(dev)
    return {'format': FORMAT, 'usb_id': '320f:506a', 'serial': dev.serial,
            'slots': info.slots, 'lighting': read_settings(dev).hex(),
            'windows_enabled': bool(read_settings(dev, 21, 1)[0]),
            'polling_rate': read_settings(dev, 22, 1)[0],
            'keymap': read_keymap(dev).hex(), 'colors': read_colors(dev).hex(),
            'macros': read_macros(dev).hex()}


def validate(data: dict, slots: int, macro_capacity: int) -> dict[str, bytes]:
    if not isinstance(data, dict) or data.get('format') != FORMAT or data.get('usb_id') != '320f:506a':
        raise ValueError('not an Akko 3098N device profile')
    if data.get('slots') != slots or type(data.get('windows_enabled')) is not bool:
        raise ValueError('profile matrix or Windows-key flag does not match')
    result = {}
    # Older v1 snapshots did not capture polling; preserve it when absent.
    if 'polling_rate' in data:
        rate = data['polling_rate']
        if type(rate) is not int or rate not in (0, 1, 2, 3):
            raise ValueError('profile polling_rate must be a selector from 0 to 3')
        result['polling_rate'] = bytes([rate])
    for field, size in [('lighting', 21), ('keymap', slots * 3), ('colors', slots * 3), ('macros', macro_capacity)]:
        if not isinstance(data.get(field), str):
            raise ValueError(f'profile {field} must be hex bytes')
        try:
            value = bytes.fromhex(data[field])
        except ValueError as exc:
            raise ValueError(f'profile {field} is not hex') from exc
        if len(value) != size:
            raise ValueError(f'profile {field} has the wrong length')
        result[field] = value
    # Decode ordinary lighting fields but retain reserved record bytes.
    from .lighting import decode
    decode(result['lighting'])
    from . import usb_macros
    bank = usb_macros.decode(result['macros'])
    usb_macros.validate_bindings(result['keymap'], bank)
    return result


def save(data: dict, path: str | Path) -> Path:
    path = Path(path)
    with path.open('x') as output:
        json.dump(data, output, indent=2)
        output.write('\n')
        output.flush()
        os.fsync(output.fileno())
    return path


def load(path: str | Path) -> dict:
    with Path(path).open() as source:
        return json.load(source)


def backup(dev: Akko3098N, path: str | None = None) -> Path:
    if path is None:
        folder = Path.cwd() / '.akko-backups'
        folder.mkdir(exist_ok=True)
        path = folder / f'{time.time_ns()}.akko.json'
    return save(capture(dev), path)


def restore(dev: Akko3098N, data: dict) -> None:
    info = device_info(dev)
    validated = validate(data, info.slots, info.macro_capacity)
    if data.get('serial') != dev.serial:
        raise ValueError('profile serial does not match the connected keyboard')
    from . import usb_macros
    active = read_keymap(dev)
    if read_macros(dev) != validated['macros']:
        usb_macros.suspend_bindings(dev, active)
        write_macros(dev, validated['macros'])
        active = read_keymap(dev)
    for offset in range(0, len(active), 3):
        value = validated['keymap'][offset:offset + 3]
        if active[offset:offset + 3] != value:
            write_keymap(dev, value, offset)
    if read_colors(dev) != validated['colors']:
        write_colors(dev, validated['colors'])
    if read_settings(dev) != validated['lighting']:
        write_lighting(dev, validated['lighting'])
    flag = bytes([int(data['windows_enabled'])])
    if read_settings(dev, 21, 1) != flag:
        write_settings_field(dev, 21, flag)
    if 'polling_rate' in validated and read_settings(dev, 22, 1) != validated['polling_rate']:
        write_settings_field(dev, 22, validated['polling_rate'])
