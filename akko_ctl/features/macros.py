"""Offline editor for archived Windows ShootData JSON files.

These files are application presets, not files stored in keyboard firmware.
Their event fields are retained without claiming a verified device playback
format. The connected 3098N's native recorder uses separate storage from the
USB macro table. Verified onboard upload/playback lives in usb_macros.py; do
not feed these archived files to that encoder.
"""

from __future__ import annotations

from dataclasses import dataclass

from akko_ctl.json_schema import load_shoot, save_shoot


@dataclass
class MacroEvent:
    """One event in a macro."""
    action: str   # "down" or "up"
    button: int   # Vendor event button/code
    delay: int    # ms to wait after this event
    type_: int    # Vendor event type


# The archived defaults contain four ShootData files
NUM_MACRO_SLOTS = 4


def list_macros() -> dict[int, dict]:
    """Load all 4 macro slots, return a dict of {slot: data}."""
    return {i: load_shoot(i) for i in range(NUM_MACRO_SLOTS)}


def get_macro(slot: int) -> dict:
    """Load a single macro slot (0..3)."""
    return load_shoot(slot)


def set_macro(slot: int, data: dict, path: str | None = None) -> None:
    """Save a macro to a slot, optionally to a custom path."""
    save_shoot(slot, data, path or f"/tmp/macro_{slot}.shoot")


def encode_events(events: list[MacroEvent]) -> dict:
    """Encode a list of MacroEvents to ShootData JSON format."""
    return {
        "Events": [
            {"Action": e.action, "Button": e.button, "Delay": e.delay, "Type": e.type_}
            for e in events
        ]
    }


def decode_events(data: dict) -> list[MacroEvent]:
    """Decode ShootData JSON to a list of MacroEvents."""
    return [
        MacroEvent(action=ev["Action"], button=ev["Button"],
                   delay=ev["Delay"], type_=ev["Type"])
        for ev in data.get("Events", [])
    ]


__all__ = [
    "NUM_MACRO_SLOTS",
    "MacroEvent",
    "decode_events",
    "encode_events",
    "get_macro",
    "list_macros",
    "set_macro",
]
