# Akko 3098N Control for Linux

A desktop app and command-line tool for the Akko 3098N mechanical keyboard
over wired USB (`320f:506a`). Configure lighting, paint and remap keys from an
interactive layout, manage onboard macros, and save and restore device profiles.

Requires Linux and Python 3.12 or later. The desktop app uses PySide6.

```sh
cd akko-3098n-ctl
python3 -m venv .venv
.venv/bin/python -m pip install '.[gui]'
.venv/bin/akko-ctl gui
```

Use wired mode and follow the [USB access setup](akko-3098n-ctl/README.md#install)
if the app cannot open the keyboard. For CLI-only use, install with
`pip install .` inside the virtual environment.

- [User guide](akko-3098n-ctl/README.md)
- [USB protocol reference](akko-3098n-ctl/docs/usb-protocol.md)
- [GPLv3 license](LICENSE)
