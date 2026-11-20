"""JSON schema helpers for reading/writing Akko's Keyboard.json and ShootData.

These files are stored in the Windows app's `DefaultData/` directory and
contain the full keymap, per-key colors, and macro definitions.
The format is documented from the extracted app bundle.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

# Path to the shipped default presets (relative to this module's location).
# This module lives at akko-3098n-ctl/akko_ctl/json_schema.py.
# The repo root (with 3098N_Firmware_driver20211217/) is two levels up.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEFAULT_DATA = os.path.join(
    _REPO_ROOT,
    "3098N_Firmware_driver20211217",
    "extractions",
    "3098N Akko Wireless Manager 12-13.exe.extracted",
    "AA9F7",
    "DefaultData",
)

_KEYBOARD_JSON  = os.path.join(_DEFAULT_DATA, "Keyboard.json")
_KEYBOA1RD_JSON = os.path.join(_DEFAULT_DATA, "Keyboa1rd.json")   # typo intentional
_DEFAULT_LIGHT   = os.path.join(_DEFAULT_DATA, "default_light.json")
_DEFAULT_GAME   = os.path.join(_DEFAULT_DATA, "DefaultGame.json")
_SHOOT_PATTERNS = [os.path.join(_DEFAULT_DATA, f"ShootData_{i}.Shoot") for i in range(4)]


# ── Keyboard.json ─────────────────────────────────────────────────────────

def load_keyboard(path: str | None = None) -> dict[str, Any]:
    """Load Keyboard.json (or a copy exported from the app)."""
    with open(path or _KEYBOARD_JSON) as f:
        return json.load(f)


def save_keyboard(data: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ── Light modes ────────────────────────────────────────────────────────────

def load_light_modes(path: str | None = None) -> list[dict]:
    """Load default_light.json, return the keyboard section (first list)."""
    with open(path or _DEFAULT_LIGHT) as f:
        return json.load(f)["DefaultLightName"][0]  # keyboard modes only


# ── ShootData macros ───────────────────────────────────────────────────────

def load_shoot(index: int, path: str | None = None) -> dict:
    """Load one of ShootData_0..3.Shoot (JSON)."""
    src = path or _SHOOT_PATTERNS[index]
    with open(src) as f:
        return json.load(f)


def save_shoot(index: int, data: dict, path: str) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


# ── ShootData event encoding ─────────────────────────────────────────────────

@dataclass
class MacroEvent:
    """One event in a ShootData macro.

    Action: "down" | "up"
    Button: 0 = keyboard, 1 = mouse
    Delay: milliseconds to wait before the next event
    Type: 1 = key down, 4 = key up, 5 = delay
    """
    Action: str   # "down" or "up"
    Button: int   # 0 = keyboard scancode, 1 = mouse button
    Delay:  int   # ms
    Type:   int   # 1=keydn 4=keyup 5=delay


def encode_macro_events(events: list[MacroEvent]) -> dict:
    """Encode a list of MacroEvents to the ShootData JSON format."""
    return {
        "MacroName": "UserMacro",
        "Version": "1.0",
        "Events": [
            {"Action": e.Action, "Button": e.Button, "Delay": e.Delay, "Type": e.Type}
            for e in events
        ],
    }


def decode_macro_events(data: dict) -> list[MacroEvent]:
    """Decode ShootData JSON to a list of MacroEvents."""
    return [
        MacroEvent(Action=ev["Action"], Button=ev["Button"],
                   Delay=ev["Delay"], Type=ev["Type"])
        for ev in data.get("Events", [])
    ]


__all__ = [
    "_DEFAULT_LIGHT",
    "_KEYBOARD_JSON",
    "MacroEvent",
    "decode_macro_events",
    "encode_macro_events",
    "load_keyboard",
    "load_light_modes",
    "load_shoot",
    "save_keyboard",
    "save_shoot",
]
