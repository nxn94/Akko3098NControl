"""Linux CLI for verified lighting control and offline vendor-file utilities."""

from __future__ import annotations

import argparse
import json
import sys

from .device import Akko3098N
from .features.keymap import (
    _TYPE_CONSUMER,
    _TYPE_MODIFIER,
    _TYPE_NORMAL,
    describe_keymap,
    load_keyboard,
    make_assignment,
    save_keyboard,
)
from .features.lighting import (
    Brightness,
    ColorRGB,
    LightingConfig,
    Mode,
    Speed,
    get_config,
    set_brightness,
    set_mode,
    set_static_color,
)
from .features.lighting import (
    apply as apply_lighting,
)
from .features.macros import (
    get_macro,
    list_macros,
)
from .features.profile import get_profile, list_profiles
from .features.system import PollingRate, set_polling_rate
from .hardware_cli import register as register_hardware_commands
from .protocol import read_settings

# ── cmd_info ──────────────────────────────────────────────────────────────

def cmd_info(_: argparse.Namespace) -> int:
    infos = Akko3098N.find()
    print(f"Found {len(infos)} HID collection(s):")
    for i, info in enumerate(infos):
        path = info["path"]
        if isinstance(path, bytes):
            path = path.decode()
        print(f"  [{i}] {path}  iface={info['interface_number']}  "
              f"page=0x{info['usage_page']:04x}  usage=0x{info['usage']:04x}")
    with Akko3098N.open_vendor() as dev:
        print("\nVendor channel:")
        print(f"  Manufacturer: {dev.manufacturer}")
        print(f"  Product:      {dev.product}")
        print(f"  Serial:       {dev.serial}")
    return 0


# ── cmd_light ────────────────────────────────────────────────────────────

def cmd_light_set(args: argparse.Namespace) -> int:
    cfg = LightingConfig(
        mode=Mode(args.mode),
        brightness=Brightness(args.brightness),
        speed=Speed(args.speed),
        random_flag=args.random,
        color=ColorRGB.from_hex(args.color),
    )
    with Akko3098N.open_vendor() as dev:
        apply_lighting(dev, cfg)
    print(f"Applied: mode={Mode(args.mode).name}, brightness={cfg.brightness.name}, "
          f"speed={int(cfg.speed)}, color={args.color}")
    return 0


def cmd_light_static(args: argparse.Namespace) -> int:
    color = ColorRGB.from_hex(args.color)
    with Akko3098N.open_vendor() as dev:
        set_static_color(dev, color)
    print(f"Set STATIC color to {args.color}")
    return 0


def cmd_light_rainbow(args: argparse.Namespace) -> int:
    if args.keys is not None:
        raise ValueError("--keys is no longer supported; rainbow uses the built-in wave effect")
    with Akko3098N.open_vendor() as dev:
        apply_lighting(dev, LightingConfig(mode=Mode.WAVE, random_flag=True))
    print("Applied built-in rainbow wave")
    return 0


def cmd_light_brightness(args: argparse.Namespace) -> int:
    with Akko3098N.open_vendor() as dev:
        set_brightness(dev, args.level)
    print(f"Brightness: {args.level}/4")
    return 0


def cmd_light_off(_: argparse.Namespace) -> int:
    with Akko3098N.open_vendor() as dev:
        set_mode(dev, Mode.OFF)
    print("Lighting off")
    return 0


def cmd_light_save(args: argparse.Namespace) -> int:
    with Akko3098N.open_vendor() as dev:
        cfg = get_config(dev)
    data = {"version": 2, "mode": cfg.mode.name.lower(), "brightness": int(cfg.brightness),
            "speed": int(cfg.speed), "random": cfg.random_flag, "color": cfg.color.to_hex()}
    # Use exclusive creation to avoid overwriting an unrelated user file.
    with open(args.file, "x") as output:
        json.dump(data, output, indent=2)
        output.write("\n")
    print(f"Saved lighting preset to {args.file}")
    return 0


def cmd_light_load(args: argparse.Namespace) -> int:
    with open(args.file) as source:
        data = json.load(source)
    if not isinstance(data, dict) or data.get("version") not in (1, 2):
        raise ValueError("expected a version 1 or 2 lighting preset")
    try:
        brightness, speed = data["brightness"], data["speed"]
        # Version 1 named the two fields in reverse. Preserve its wire values.
        if data["version"] == 1:
            brightness, speed = speed, brightness
        cfg = LightingConfig(mode=parse_mode(data["mode"]), brightness=brightness,
                             speed=speed, random_flag=data["random"],
                             color=ColorRGB.from_hex(data["color"]))
    except (KeyError, TypeError, argparse.ArgumentTypeError) as exc:
        raise ValueError(f"invalid lighting preset: {exc}") from exc
    with Akko3098N.open_vendor() as dev:
        apply_lighting(dev, cfg)
    print(f"Applied lighting preset from {args.file}")
    return 0


# ── cmd_system ───────────────────────────────────────────────────────────

def cmd_system_polling(args: argparse.Namespace) -> int:
    rate_map = {"125": PollingRate.HZ_125, "250": PollingRate.HZ_250,
                "500": PollingRate.HZ_500, "1000": PollingRate.HZ_1000}
    with Akko3098N.open_vendor() as dev:
        from .features.snapshot import backup
        path = backup(dev, args.backup)
        print(f'Backup: {path.resolve()}', flush=True)
        set_polling_rate(dev, rate_map[args.hz])
    print(f"Configured polling rate: {args.hz} Hz (readback verified)")
    return 0


# ── cmd_keymap ───────────────────────────────────────────────────────────

def cmd_keymap_describe(args: argparse.Namespace) -> int:
    kb = load_keyboard(args.file)
    entries = describe_keymap(kb)
    for slot, name, default in entries:
        marker = " ←" if name != default else ""
        print(f"  [{slot:3d}] {name}{marker}")
    return 0


def cmd_keymap_export(args: argparse.Namespace) -> int:
    kb = load_keyboard(args.file)
    save_keyboard(kb, args.output)
    print(f"Exported keymap to {args.output}")
    return 0


def cmd_keymap_import(args: argparse.Namespace) -> int:
    kb = load_keyboard(args.file)
    save_keyboard(kb, args.output)
    print(f"Imported keymap from {args.file} to {args.output}")
    return 0


def cmd_keymap_set(args: argparse.Namespace) -> int:
    kb = load_keyboard(args.keymap)
    keys = kb["Device"][0]["KeyList"]
    if args.slot < 0 or args.slot >= len(keys):
        print(f"Slot {args.slot} out of range (0..{len(keys)-1})")
        return 1
    # Allow bare scancode or "mod:scancode" for modifiers
    scancode: int
    if args.target.startswith("mod:"):
        scancode = int(args.target[4:], 0)
        type_ = _TYPE_MODIFIER
    elif args.target.startswith("consumer:"):
        scancode = int(args.target[9:], 0)
        type_ = _TYPE_CONSUMER
    else:
        scancode = int(args.target, 0)
        type_ = _TYPE_NORMAL
    keys[args.slot]["Assignment"] = make_assignment(scancode, type_)
    if args.keymap is None:
        raise ValueError("--keymap PATH is required; this edits a JSON file, not the keyboard")
    save_keyboard(kb, args.keymap)
    print(f"Updated file {args.keymap}: slot {args.slot} → scancode 0x{scancode:02x} (type=0x{type_:02x})")
    return 0


# ── cmd_profile ──────────────────────────────────────────────────────────

def cmd_profile_list(_: argparse.Namespace) -> int:
    kb = load_keyboard()
    for p in list_profiles(kb):
        print(f"  [{p.index}] {'(game)' if p.is_game else '(base)'} {p.name}  uuid={p.uuid}")
    return 0


def cmd_profile_show(args: argparse.Namespace) -> int:
    kb = load_keyboard()
    p = list_profiles(kb)[args.index]
    dev = get_profile(kb, args.index)
    print(f"Profile {args.index}: {p.name}")
    print(f"  Keys: {len(dev['KeyList'])}")
    print(f"  LightInfo mode: {dev.get('LightInfo', {}).get('Fx', '?')}")
    print(f"  SystemStages: {dev.get('SystemStages', {})}")
    return 0


# ── cmd_macro ────────────────────────────────────────────────────────────

def cmd_macro_list(_: argparse.Namespace) -> int:
    for slot, data in list_macros().items():
        n = len(data.get("Events", []))
        name = data.get("MacroName") or "(no name)"
        print(f"  [{slot}] {name}  {n} events")
    return 0


def cmd_macro_show(args: argparse.Namespace) -> int:
    data = get_macro(args.slot)
    events = data.get("Events", [])
    print(f"Macro slot {args.slot}: {len(events)} events")
    for ev in events[:20]:
        print(f"  {ev['Action']:4s}  button=0x{ev['Button']:04x}  delay={ev['Delay']}ms  type={ev['Type']}")
    if len(events) > 20:
        print(f"  ... (+{len(events)-20} more)")
    return 0


# ── Argument parser ───────────────────────────────────────────────────────

def parse_mode(value: str) -> Mode:
    aliases = {"breath": Mode.BREATHING, "wave_short": Mode.WAVE}
    try:
        name = value.lower().replace("-", "_")
        if name in aliases:
            return aliases[name]
        if name.upper() in Mode.__members__:
            return Mode[name.upper()]
        return Mode(int(value, 0))
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"unknown mode: {value}; run light modes") from exc


def cmd_light_status(args: argparse.Namespace) -> int:
    with Akko3098N.open_vendor() as dev:
        if args.raw:
            data = read_settings(dev, size=256)
        else:
            cfg = get_config(dev)
    if args.raw:
        for offset in range(0, len(data), 16):
            print(f"{offset:04x}: {data[offset:offset + 16].hex(' ')}")
    else:
        print(f"Mode: {cfg.mode.name.lower().replace('_', '-')}")
        print(f"Brightness: {int(cfg.brightness)}/4")
        print(f"Speed: {int(cfg.speed)}/4")
        print(f"Color: {cfg.color.to_hex()}")
        print(f"Multicolor: {'on' if cfg.random_flag else 'off'}")
    return 0


def cmd_light_modes(_: argparse.Namespace) -> int:
    for mode in Mode:
        print(f"{mode.value:2d}  {mode.name.lower().replace('_', '-')}")
    return 0


def cmd_gui(_: argparse.Namespace) -> int:
    try:
        from .desktop import run
    except ImportError as exc:
        raise RuntimeError(f"Desktop UI requires Qt. Install the gui extra with pip install '.[gui]'. ({exc})") from exc
    return run()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="akko-ctl",
        description="Linux control tool for the Akko 3098N keyboard.")
    sub = p.add_subparsers(dest="cmd", required=True)

    # info
    p_info = sub.add_parser("info", help="Show device identity")
    p_info.set_defaults(func=cmd_info)
    sub.add_parser("gui", help="Open the desktop keyboard editor").set_defaults(func=cmd_gui)

    # light
    p_light = sub.add_parser("light", help="Lighting modes, colors, brightness and presets")
    sp = p_light.add_subparsers(dest="light_cmd", required=True)

    ps = sp.add_parser("set", help="Set mode, color, brightness and speed")
    ps.add_argument("mode", type=parse_mode, metavar="MODE", choices=list(Mode),
                   help="Mode name (wave, breathing, static, …) or number; see light modes")
    ps.add_argument("--color", default="#ffffff", help="#RRGGBB")
    ps.add_argument("--brightness", type=int, default=Brightness.HIGHEST,
                     choices=[b.value for b in Brightness])
    ps.add_argument("--speed", type=int, default=Speed.NORMAL, choices=[s.value for s in Speed])
    ps.add_argument("--random", action="store_true")
    ps.set_defaults(func=cmd_light_set)

    p_status = sp.add_parser("status", help="Read current lighting settings")
    p_status.add_argument("--raw", action="store_true", help="Show raw settings bytes")
    p_status.set_defaults(func=cmd_light_status)
    sp.add_parser("modes", help="List lighting modes").set_defaults(func=cmd_light_modes)

    p_st = sp.add_parser("static", help="Set STATIC mode + color")
    p_st.add_argument("color")
    p_st.set_defaults(func=cmd_light_static)

    p_rr = sp.add_parser("rainbow", help="Use the built-in multicolor wave")
    p_rr.add_argument("--keys", type=int, default=None, help=argparse.SUPPRESS)
    p_rr.set_defaults(func=cmd_light_rainbow)

    p_level = sp.add_parser("brightness", help="Change brightness, keeping the current effect")
    p_level.add_argument("level", type=int, choices=range(5))
    p_level.set_defaults(func=cmd_light_brightness)
    sp.add_parser("off", help="Turn off lighting").set_defaults(func=cmd_light_off)
    for name, action in (("save", cmd_light_save), ("load", cmd_light_load)):
        preset = sp.add_parser(name, help=f"{name.capitalize()} a lighting preset JSON file")
        preset.add_argument("file")
        preset.set_defaults(func=action)


    # system
    p_sys = sub.add_parser("system", help="System settings")
    sp2 = p_sys.add_subparsers(dest="sys_cmd", required=True)
    p_polling = sp2.add_parser("polling", help="Set configured USB polling rate")
    p_polling.add_argument("hz", choices=["125","250","500","1000"])
    p_polling.add_argument('--backup', help='Backup JSON path (default: .akko-backups/<timestamp>.akko.json)')
    p_polling.set_defaults(func=cmd_system_polling)

    # keymap
    p_km = sub.add_parser("keymap", help="Live keymap commands plus legacy JSON utilities")
    sp3 = p_km.add_subparsers(dest="km_cmd", required=True)

    p_describe = sp3.add_parser("describe", help="Show keymap")
    p_describe.add_argument("--file", default=None)
    p_describe.set_defaults(func=cmd_keymap_describe)

    p_exp = sp3.add_parser("export", help="Export Keyboard.json")
    p_exp.add_argument("output")
    p_exp.add_argument("--file", default=None)
    p_exp.set_defaults(func=cmd_keymap_export)

    p_imp = sp3.add_parser("import", help="Import Keyboard.json")
    p_imp.add_argument("output")
    p_imp.add_argument("--file", default=None)
    p_imp.set_defaults(func=cmd_keymap_import)

    p_set = sp3.add_parser("set", help="Edit a key assignment in a JSON file only")
    p_set.add_argument("slot", type=int)
    p_set.add_argument("target", help="scancode or mod:scancode")
    p_set.add_argument("--keymap", required=True)
    p_set.set_defaults(func=cmd_keymap_set)

    # profile
    p_pr = sub.add_parser("profile", help="Save and apply local device profiles")
    sp4 = p_pr.add_subparsers(dest="pr_cmd", required=True)
    sp4.add_parser("vendor-list", help="List archived vendor profiles (offline)").set_defaults(func=cmd_profile_list)
    p_prshow = sp4.add_parser("vendor-show", help="Show archived vendor profile details (offline)")
    p_prshow.add_argument("index", type=int)
    p_prshow.set_defaults(func=cmd_profile_show)

    # macro
    p_mac = sub.add_parser("macro", help="Onboard macros plus archived vendor-file utilities")
    sp5 = p_mac.add_subparsers(dest="mac_cmd", required=True)
    sp5.add_parser("vendor-list", help="List archived Windows macros (offline)").set_defaults(func=cmd_macro_list)
    p_macshow = sp5.add_parser("vendor-show", help="Show archived Windows macro events (offline)")
    p_macshow.add_argument("slot", type=int, choices=[0,1,2,3])
    p_macshow.set_defaults(func=cmd_macro_show)

    register_hardware_commands(sp, sp2, sp3, sp4)
    from .macro_cli import register
    register(sp5)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not hasattr(args, "func"):
        build_parser().print_help()
        return 1
    try:
        return args.func(args)
    except (OSError, RuntimeError, ValueError, IndexError) as exc:
        print(f"akko-ctl: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("akko-ctl: interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
