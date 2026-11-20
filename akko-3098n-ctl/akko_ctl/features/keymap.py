"""Keymap feature: rebind keys, encode/decode Assignment integers, export/import JSON.

The Assignment field is a 32-bit integer encoding the HID scancode and
modifier type. Decoded from `Keyboard.json` (126 entries in
`Device[0].KeyList[]`):

    Assignment = (type << 24) | (row << 16) | scancode

Types (top byte):
    0x00  Normal key scancode (HID Usage ID, USB HID Table 12)
    0x30  Modifier key (LCtrl=0xE0 .. RGUI=0xE7, Shift/Ctrl/Alt/Win × L/R)
    0xa0  Consumer media key (Mute=0xE2, VolUp=0xEA, VolDn=0xAE, ...)
    0xd0  Special (boot keyboard not supported, system sleep/wake/...)

The second byte (row) is always 0x20 for normal keys, 0x00 for everything else.

Known scancodes (from the 98-key layout in `keyboarddevice.xml`):
    0x00-0x03  system
    0x04  a/A
    0x05-0x1e  letters B-Z
    0x1f  1/!
    ...
    0x27  0/right-paren
    0x28  Enter
    0x29  Escape
    0x2a  Backspace
    0x2b  Tab
    0x2c  Space
    0x2d-0x38  - = [ ] \\ ; ' ` , . /
    0x39  CapsLock
    0x3a-0x45  F1-F12
    0x46  PrintScreen
    0x47  ScrollLock
    0x48  Pause
    0x49  Insert
    0x4a  Home
    0x4b  PageUp
    0x4c  Delete
    0x4d  End
    0x4e  PageDown
    0x4f  RightArrow
    0x50  LeftArrow
    0x51  DownArrow
    0x52  UpArrow
    0x53  Keypad NumLock
    0x54-0x5e  KP / * - + Enter .
    0x5f-0x63  keypad 1-9, 0

Modifier scancodes:
    0xE0 LCtrl  0xE1 LShift  0xE2 LAlt  0xE3 LGUI
    0xE4 RCtrl  0xE5 RShift  0xE6 RAlt  0xE7 RGUI

Consumer (type=0xA0):
    0x00  Unassigned
    0x01  Consumer Controls
    0x20  -10
    0x21  +10
    0x22  0
    0x30  Play/Pause
    0x7F  Mute
    0x80  Vol-
    0x81  Vol+
    0xB0  Scan Next Track
    0xB5  Scan Prev Track
    0xB6  Stop
    0xB7  Random Play
    0xB8  Repeat
    0xCD  Play
    0xE2  Mute
    0xE9  Vol+
    0xEA  Vol-
    0xEF  Brightness+
    0xF0  Brightness-
"""

from __future__ import annotations

from akko_ctl.json_schema import load_keyboard, save_keyboard

# ── Assignment encoding ──────────────────────────────────────────────────

_TYPE_NORMAL    = 0x00
_TYPE_MODIFIER = 0x30
_TYPE_CONSUMER = 0xa0
_TYPE_SPECIAL  = 0xd0


def make_assignment(scancode: int, type_: int = _TYPE_NORMAL) -> int:
    """Encode a scancode into an Assignment integer.

    Normal keys: type=0x00, row=0x20
    Modifiers:   type=0x30, row=0x00
    Consumer:    type=0xA0, row=0x00
    """
    if type_ == _TYPE_NORMAL:
        return (type_ << 24) | (0x20 << 16) | (scancode & 0xFF)
    else:
        return (type_ << 24) | (0x00 << 16) | (scancode & 0xFF)


def parse_assignment(a: int) -> tuple[int, int, int]:
    """Decode an Assignment integer into (type_, row, scancode)."""
    type_    = (a >> 24) & 0xFF
    row       = (a >> 16) & 0xFF
    scancode  = a & 0xFFFF
    return type_, row, scancode


def scancode_name(scancode: int, type_: int) -> str:
    """Human-readable name for a scancode."""
    if type_ == _TYPE_MODIFIER:
        names = {0xE0:"LCtrl", 0xE1:"LShift", 0xE2:"LAlt", 0xE3:"LGui",
                 0xE4:"RCtrl", 0xE5:"RShift", 0xE6:"RAlt", 0xE7:"RGui"}
        return names.get(scancode & 0xFF, f"Modifier(0x{scancode:02x})")
    elif type_ == _TYPE_CONSUMER:
        names = {0xE2:"Mute", 0xE9:"VolUp", 0xEA:"VolDown", 0x7F:"Mute",
                 0x80:"VolDown", 0x81:"VolUp", 0xB0:"NextTrack", 0xB5:"PrevTrack",
                 0xB6:"Stop", 0xCD:"Play", 0x30:"PlayPause", 0x20:"-10", 0x21:"+10"}
        return names.get(scancode & 0xFF, f"Consumer(0x{scancode:02x})")
    else:
        # Standard HID keyboard usage table
        names = {
            0x04:"a", 0x05:"b", 0x06:"c", 0x07:"d", 0x08:"e", 0x09:"f",
            0x0a:"g", 0x0b:"h", 0x0c:"i", 0x0d:"j", 0x0e:"k", 0x0f:"l",
            0x10:"m", 0x11:"n", 0x12:"o", 0x13:"p", 0x14:"q", 0x15:"r",
            0x16:"s", 0x17:"t", 0x18:"u", 0x19:"v", 0x1a:"w", 0x1b:"x",
            0x1c:"y", 0x1d:"z",
            0x1e:"1", 0x1f:"2", 0x20:"3", 0x21:"4", 0x22:"5", 0x23:"6",
            0x24:"7", 0x25:"8", 0x26:"9", 0x27:"0",
            0x28:"Enter", 0x29:"Escape", 0x2a:"Backspace", 0x2b:"Tab",
            0x2c:"Space",
            0x2d:"-", 0x2e:"=", 0x2f:"[", 0x30:"]", 0x31:"\\",
            0x32:"#~", 0x33:";'", 0x34:"`'",
            0x35:",", 0x36:".", 0x37:"/",
            0x38:"CapsLock",
            0x39:"F1", 0x3a:"F2", 0x3b:"F3", 0x3c:"F4",
            0x3d:"F5", 0x3e:"F6", 0x3f:"F7", 0x40:"F8",
            0x41:"F9", 0x42:"F10", 0x43:"F11", 0x44:"F12",
        }
        return names.get(scancode, f"Scancode(0x{scancode:02x})")


# ── JSON keymap operations ───────────────────────────────────────────────

def rebind_key(keymap: dict, slot: int, new_scancode: int,
               type_: int = _TYPE_NORMAL) -> None:
    """Set KeyList[slot].Assignment in a loaded Keyboard.json dict."""
    keys = keymap["Device"][0]["KeyList"]
    keys[slot]["Assignment"] = make_assignment(new_scancode, type_)


def get_key_assignment(keymap: dict, slot: int) -> int:
    """Get the current Assignment value for a slot."""
    return keymap["Device"][0]["KeyList"][slot]["Assignment"]


def describe_keymap(keymap: dict) -> list[tuple[int, str, str]]:
    """Return a list of (slot, scancode_name, default_name) for all 126 keys."""
    result = []
    keys = keymap["Device"][0]["KeyList"]
    for slot, k in enumerate(keys):
        a = k["Assignment"]
        type_, _row, sc = parse_assignment(a)
        name = scancode_name(sc, type_)
        da = k["DefaultAssignment"]
        dt, _dr, ds = parse_assignment(da)
        default_name = scancode_name(ds, dt)
        result.append((slot, name, default_name))
    return result


__all__ = [
    "_TYPE_CONSUMER",
    "_TYPE_MODIFIER",
    "_TYPE_NORMAL",
    "_TYPE_SPECIAL",
    "describe_keymap",
    "get_key_assignment",
    "load_keyboard",
    "make_assignment",
    "parse_assignment",
    "rebind_key",
    "save_keyboard",
    "scancode_name",
]
