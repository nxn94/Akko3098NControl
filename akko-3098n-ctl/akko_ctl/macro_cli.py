"""Backup-first CLI for the verified onboard one-shot keyboard macro format."""

from __future__ import annotations

import json

from .device import Akko3098N
from .features import live_keymap, snapshot
from .features import usb_macros as macros
from .hardware_cli import _add_backup, _backup
from .protocol import device_info, read_keymap, read_macros


def create(args):
    events = macros.sequence(args.keys, args.delay_ms, args.repeat)
    snapshot.save(macros.export([events]), args.file)
    print(f'Created {args.file}: {len(events)} events')
    return 0


def read(args):
    with Akko3098N.open_vendor() as dev:
        bank = macros.decode(read_macros(dev))
    if args.action == 'export':
        snapshot.save(macros.export(bank), args.file)
        print(f'Exported {len(bank)} macro slots to {args.file}')
    elif args.action == 'show':
        if not 0 <= args.index < len(bank):
            raise ValueError('macro index does not exist')
        print(json.dumps(macros.export([bank[args.index]])['macros'][0], indent=2))
    else:
        for index, events in enumerate(bank):
            print(f'{index}: {len(events)} events, {sum(e.delay_ms for e in events)} ms')
        if not bank:
            print('No USB macros stored')
    return 0


def upload(args):
    bank = macros.parse(snapshot.load(args.file))
    with Akko3098N.open_vendor() as dev:
        macros.encode(bank, device_info(dev).macro_capacity)
        macros.validate_bindings(read_keymap(dev), bank)
        _backup(dev, args)
        macros.upload(dev, bank)
    print('Onboard macro bank uploaded and verified')
    return 0


def bind(args):
    with Akko3098N.open_vendor() as dev:
        bank = macros.decode(read_macros(dev))
        factory = read_keymap(dev, factory=True)
        if not 0 <= args.slot < len(factory) // 3 or factory[3 * args.slot] != 0x20:
            raise ValueError('slot is empty or protected')
        if not 0 <= args.index < len(bank) or not bank[args.index]:
            raise ValueError('macro index is missing or empty')
        _backup(dev, args)
        macros.bind(dev, args.slot, args.index)
    print(f'Slot {args.slot} plays macro {args.index} once (readback verified)')
    return 0


def unbind(args):
    with Akko3098N.open_vendor() as dev:
        active = read_keymap(dev)
        factory = read_keymap(dev, factory=True)
        offset = args.slot * 3
        if not 0 <= args.slot < len(active) // 3 or active[offset] not in (0x70, 0x71):
            raise ValueError('slot is not bound to a macro')
        target = live_keymap.Assignment.from_bytes(factory[offset:offset + 3])
        if target.kind != 0x20:
            raise ValueError('factory slot is protected')
        _backup(dev, args)
        live_keymap.rebind(dev, args.slot, target)
    print(f'Slot {args.slot}: factory assignment restored and verified')
    return 0


def remove(args):
    with Akko3098N.open_vendor() as dev:
        bank = macros.decode(read_macros(dev))
        if not 0 <= args.index < len(bank):
            raise ValueError('macro index does not exist')
        bank[args.index] = []
        while bank and not bank[-1]:
            bank.pop()
        macros.validate_bindings(read_keymap(dev), bank)
        _backup(dev, args)
        macros.upload(dev, bank)
    print(f'Macro {args.index} removed; other indices preserved (readback verified)')
    return 0


def register(commands):
    parser = commands.add_parser('create', help='Create an uploadable macro JSON from key names')
    parser.add_argument('file')
    parser.add_argument('keys', nargs='+', help='Key names, chords, or mouse buttons, e.g. left-shift+b mouse:left')
    parser.add_argument('--delay-ms', type=int, default=100)
    parser.add_argument('--repeat', type=int, default=1, help='Play the sequence this many times per trigger')
    parser.set_defaults(func=create)
    for name in ('list', 'show', 'export'):
        parser = commands.add_parser(name, help=f'{name.capitalize()} actual onboard USB macros')
        parser.set_defaults(func=read, action=name)
        if name == 'show':
            parser.add_argument('index', type=int)
        elif name == 'export':
            parser.add_argument('file')
    for name, action in [('upload', upload), ('bind', bind), ('unbind', unbind), ('remove', remove)]:
        parser = commands.add_parser(name, help=f'{name.capitalize()} onboard macros (backs up first)')
        parser.set_defaults(func=action)
        _add_backup(parser)
        if name == 'upload':
            parser.add_argument('file')
        if name in ('bind', 'unbind'):
            parser.add_argument('slot', type=int)
        if name in ('bind', 'remove'):
            parser.add_argument('index', type=int)
