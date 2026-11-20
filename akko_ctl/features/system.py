"""Windows-key control and vendor keyboard polling-rate selector."""

from __future__ import annotations

from ..device import Akko3098N
from ..protocol import PollingRate, ProtocolError, read_settings, write_settings_field


def windows_enabled(dev: Akko3098N) -> bool:
    return bool(read_settings(dev, 21, 1)[0])


def set_win_lock(dev: Akko3098N, locked: bool) -> None:
    # Confirmed by Fn+left Windows changing settings byte 21 from 1 to 0.
    flag = bytes([int(not locked)])
    if read_settings(dev, 21, 1) != flag:
        write_settings_field(dev, 21, flag)


def set_polling_rate(dev: Akko3098N, rate: PollingRate) -> None:
    rate = PollingRate(rate)
    value = bytes([rate])
    if read_settings(dev, 22, 1) != value:
        write_settings_field(dev, 22, value)


def polling_rate(dev: Akko3098N) -> PollingRate:
    try:
        return PollingRate(read_settings(dev, 22, 1)[0])
    except ValueError as exc:
        raise ProtocolError('Unknown polling-rate selector in settings byte 22') from exc


__all__ = ['PollingRate', 'polling_rate', 'set_polling_rate', 'set_win_lock', 'windows_enabled']
