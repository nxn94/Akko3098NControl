"""Profile feature: load/save/select profiles stored in Keyboard.json format.

A profile is one element in `Device[]` in Keyboard.json, containing:
- KeyList (126 entries)
- LightInfo (lighting mode config)
- CustomLightMode (per-key color matrix)
- SystemStages (polling, repeat, WinFlag, Key6Flag, WFlag)

The Windows app stores 1 keyboard + 4 game profile slots in one Keyboard.json.
We support reading all of them and exporting/editing individual profiles.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from akko_ctl.json_schema import load_keyboard


@dataclass
class ProfileInfo:
    index: int
    is_game: bool
    name: str
    uuid: str


def list_profiles(kb: dict | None = None) -> list[ProfileInfo]:
    """List all profiles in a Keyboard.json dict."""
    kb = kb or load_keyboard()
    results = []
    for i, dev in enumerate(kb.get("Device", [])):
        name = dev.get("profile_name", f"Profile {i}")
        uuid_ = dev.get("profileUUID", "")
        is_game = bool(dev.get("game_mode", False))
        results.append(ProfileInfo(index=i, is_game=is_game, name=name, uuid=uuid_))
    return results


def get_profile(kb: dict, index: int) -> dict:
    """Get a single profile dict by index."""
    return kb["Device"][index]


def save_profile(kb: dict, index: int, data: dict) -> None:
    """Replace profile at index with new data."""
    kb["Device"][index] = data


def new_profile(name: str = "New Profile", *, game: bool = False) -> dict:
    """Create a new blank profile from a loaded Keyboard.json structure."""
    base = load_keyboard()
    profile = base["Device"][0].copy()
    profile["profile_name"] = name
    profile["profileUUID"] = str(uuid.uuid4()).upper()
    if game:
        profile["game_mode"] = True
        profile["game_uuid"] = str(uuid.uuid4()).upper()
    return profile


__all__ = ["ProfileInfo", "get_profile", "list_profiles", "new_profile", "save_profile"]
