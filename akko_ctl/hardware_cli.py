"""CLI commands for live keymaps, custom colors, backups and local profiles."""

from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from .device import Akko3098N
from .features import live_keymap, snapshot
from .features.lighting import ColorRGB, set_key_color, set_per_key
from .features.system import polling_rate, set_win_lock, windows_enabled
from .protocol import device_info, read_colors, read_keymap, read_macros, write_keymap


def _backup(dev, args) -> None:
    path = snapshot.backup(dev, getattr(args, 'backup', None))
    print(f'Backup: {path.resolve()}', flush=True)


def super_fix(_args) -> int:
    rule = files('akko_ctl').joinpath('90-akko-3098n-phantom-keys.hwdb')
    print(rule.read_text(encoding='utf-8'), end='')
    return 0


def keymap_read(args) -> int:
    with Akko3098N.open_vendor() as dev:
        for slot, original, current in live_keymap.describe(dev):
            suffix = f' (factory: {original.describe()})' if original != current else ''
            print(f'{slot:3d}  {current.describe()}{suffix}')
    return 0


def keymap_bind(args) -> int:
    target = live_keymap.parse_target(args.target)
    with Akko3098N.open_vendor() as dev:
        # Validate slot before creating a backup or issuing a write.
        slots = {slot: original for slot, original, _ in live_keymap.describe(dev)}
        if args.slot not in slots or slots[args.slot].kind != 0x20:
            raise ValueError('slot is empty or a protected special function key')
        _backup(dev, args)
        live_keymap.rebind(dev, args.slot, target)
    print(f'Applied slot {args.slot}: {target.describe()} (readback verified)')
    return 0


def keymap_restore(args) -> int:
    data = snapshot.load(args.file)
    with Akko3098N.open_vendor() as dev:
        info = device_info(dev)
        fields = snapshot.validate(data, info.slots, info.macro_capacity)
        if data.get('serial') != dev.serial:
            raise ValueError('profile serial does not match')
        if any(fields['keymap'][i] in (0x70, 0x71) for i in range(0, len(fields['keymap']), 3)):
            if read_macros(dev) != fields['macros']:
                raise ValueError('macro bindings need matching macro storage; use profile load instead')
        _backup(dev, args)
        active = read_keymap(dev)
        for offset in range(0, len(active), 3):
            entry = fields['keymap'][offset:offset + 3]
            if active[offset:offset + 3] != entry:
                write_keymap(dev, entry, offset)
    print('Keymap restored and verified; other settings preserved')
    return 0


def profile_save(args) -> int:
    with Akko3098N.open_vendor() as dev:
        snapshot.save(snapshot.capture(dev), args.file)
    print(f'Saved device profile to {args.file}')
    return 0


def profile_load(args) -> int:
    data = snapshot.load(args.file)
    with Akko3098N.open_vendor() as dev:
        info = device_info(dev)
        snapshot.validate(data, info.slots, info.macro_capacity)
        _backup(dev, args)
        snapshot.restore(dev, data)
    print('Device profile applied and verified')
    return 0


def profile_list(args) -> int:
    for path in sorted(Path(args.directory).glob('*.json')):
        try:
            data = snapshot.load(path)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get('format') == snapshot.FORMAT:
            print(path)
    return 0


def win_lock(args) -> int:
    with Akko3098N.open_vendor() as dev:
        _backup(dev, args)
        set_win_lock(dev, args.state == 'on')
    print(f'Windows-key lock {args.state} (readback verified)')
    return 0


def system_status(args) -> int:
    with Akko3098N.open_vendor() as dev:
        enabled = windows_enabled(dev)
        rate = polling_rate(dev)
    print(f'Windows key: {"enabled" if enabled else "locked"}')
    print(f'Configured polling rate: {rate.name.removeprefix("HZ_")} Hz')
    return 0


def light_key(args) -> int:
    color = ColorRGB.from_hex(args.color)
    with Akko3098N.open_vendor() as dev:
        _backup(dev, args)
        set_key_color(dev, args.slot, color)
    print(f'Slot {args.slot}: {color.to_hex()} (custom mode; readback verified)')
    return 0


def light_fill(args) -> int:
    color = ColorRGB.from_hex(args.color)
    with Akko3098N.open_vendor() as dev:
        count = device_info(dev).slots
        _backup(dev, args)
        set_per_key(dev, [color] * count)
    print(f'Custom matrix filled {color.to_hex()} (readback verified)')
    return 0


def light_colors(args) -> int:
    with Akko3098N.open_vendor() as dev:
        colors = read_colors(dev)
    for offset in range(0, len(colors), 3):
        print(f'{offset // 3:3d}  #{colors[offset:offset + 3].hex()}')
    return 0


def _add_backup(parser):
    parser.add_argument('--backup', help='Backup JSON path (default: .akko-backups/<timestamp>.akko.json)')


def register(lighting, system, keymap, profiles):
    for name, action, help_ in [
        ('read', keymap_read, 'Read live matrix slots and assignments'),
        ('bind', keymap_bind, 'Rebind a live matrix slot, backing up first'),
        ('backup', profile_save, 'Back up the actual connected keyboard'),
        ('restore', keymap_restore, 'Restore only the keymap from a device backup'),
    ]:
        parser = keymap.add_parser(name, help=help_)
        parser.set_defaults(func=action)
        if name == 'bind':
            parser.add_argument('slot', type=int)
            parser.add_argument('target', help='Key name, HID usage, modifier, chord such as left-ctrl+c, or media key such as media:mute')
            _add_backup(parser)
        elif name in ('backup', 'restore'):
            parser.add_argument('file')
            if name == 'restore':
                _add_backup(parser)

    parser = system.add_parser('win-lock', help='Enable/disable the Windows-key lock')
    parser.add_argument('state', choices=('on', 'off'))
    _add_backup(parser)
    parser.set_defaults(func=win_lock)
    system.add_parser('status', help='Read Windows-key lock state').set_defaults(func=system_status)
    system.add_parser(
        'super-fix', help='Print the Linux hwdb rule for intermittent Super-only shortcuts',
    ).set_defaults(func=super_fix)

    for name, action in [('key', light_key), ('fill', light_fill), ('colors', light_colors)]:
        parser = lighting.add_parser(name, help={'key': 'Set one matrix slot color', 'fill': 'Fill custom colors',
                                               'colors': 'Read custom LED colors'}[name])
        parser.set_defaults(func=action)
        if name != 'colors':
            if name == 'key':
                parser.add_argument('slot', type=int)
            parser.add_argument('color', help='#RRGGBB')
            _add_backup(parser)

    for name, action in [('save', profile_save), ('load', profile_load), ('list', profile_list)]:
        parser = profiles.add_parser(name, help=f'{name.capitalize()} local device profiles')
        parser.set_defaults(func=action)
        if name == 'list':
            parser.add_argument('directory', nargs='?', default='.')
        else:
            parser.add_argument('file')
            if name == 'load':
                _add_backup(parser)
