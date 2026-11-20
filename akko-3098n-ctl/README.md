# akko-3098n-ctl

Native Linux control for the **Akko 3098N**, USB `320f:506a`.
Uses the kernel's hidraw interface without detaching the keyboard driver.
The CLI requires Python 3.12 or later and has no third-party runtime dependencies.

## Install

```sh
cd akko-3098n-ctl
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/akko-ctl info
```

Use wired mode (Fn+6, rear switch in middle). For persistent desktop access:

```sh
sudo install -m 644 packaging/udev/70-akko-3098n.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
```

Reconnect after installing the rule. The active desktop user receives access
to the vendor interface only. Run the tool as your normal user.

## Desktop UI

```sh
.venv/bin/python -m pip install '.[gui]'
.venv/bin/akko-ctl gui
```

The desktop editor has tabs for lighting, key remaps and per-key RGB, onboard
macros, profiles, and system settings. It uses the same USB commands and readback
checks as the CLI. Choose **Refresh device** after reconnecting. The UI saves
a profile before each device edit in
`$XDG_STATE_HOME/akko-3098n-ctl/backups` (defaulting to `~/.local/state` when
`XDG_STATE_HOME` is unset). Use the Profiles tab to load a backup.

In **Keymap**, click keys on the virtual 3098N to select or deselect them.
Use **Set color…** to apply one RGB color to the selection and activate the
Custom effect. Use **Apply remap** to give each selected key the same assignment.
**Restore factory** restores each key's own original assignment.

## Fix intermittent Super taps on KDE

If Super+E and Alt+F1 work but tapping Super alone rarely opens the launcher,
the Akko may be sending extra consumer-control events. The bundled Linux hwdb
rule suppresses the four stray scan codes observed alongside Super and Enter on
the USB 3098N (320f:506a). This workaround restored standalone Super on the
tested keyboard.

```sh
.venv/bin/akko-ctl system super-fix > 90-akko-3098n-phantom-keys.hwdb &&
  sudo install -m 644 90-akko-3098n-phantom-keys.hwdb /etc/udev/hwdb.d/ &&
  sudo systemd-hwdb update
```

Unplug and reconnect the keyboard, then try a few slow Super taps. The CLI
command prints the rule and can run without the keyboard attached. To undo
the fix, remove `/etc/udev/hwdb.d/90-akko-3098n-phantom-keys.hwdb`, run
`sudo systemd-hwdb update` again, and reconnect.

## Lighting

```sh
.venv/bin/akko-ctl light status
.venv/bin/akko-ctl light static '#ff0000'
.venv/bin/akko-ctl light set static --color '#00ff00' --brightness 3
.venv/bin/akko-ctl light set breathing --color '#0080ff' --speed 2
.venv/bin/akko-ctl light rainbow
.venv/bin/akko-ctl light brightness 2
.venv/bin/akko-ctl light off
.venv/bin/akko-ctl light modes
.venv/bin/akko-ctl light save green.json
.venv/bin/akko-ctl light load green.json
```

Brightness is 0..4 (off to brightest). Speed is 0..4 (slowest to fastest). `static` uses maximum
brightness. `set` applies mode/color/brightness/speed together. `brightness`
preserves the other settings. `--random` selects multicolor for supported
effects. Some effects ignore color or speed, as in the vendor application.

`rainbow` uses the built-in wave effect. It does not upload a per-key matrix.
`modes` lists vendor mode names; static color has been visually confirmed on the
connected keyboard. Other mode names come from the vendor preset list.
Static is mode **1**, breathing is **3**, and wave is **18**.

Each change reads the active 21-byte record, changes only known lighting fields,
then verifies it by reading it back. Unchanged settings cause no write. The tool
checks complete replies and device errors, serializes concurrent tool instances,
and never sends the rejected BEGIN/END commands. It does not retry uncertain
writes. The tested 3098N retained its lighting settings after a USB unplug
and reconnect.

Lighting presets are saved as version 2 JSON. The loader also supports version
1 and preserves the original appearance of those presets. Saving refuses to
overwrite an existing file. `light status --raw` prints the first 256 settings bytes.

## Keymaps, custom colors, and profiles

```sh
.venv/bin/akko-ctl keymap read
.venv/bin/akko-ctl keymap bind 106 b
.venv/bin/akko-ctl keymap bind 106 kp-1
.venv/bin/akko-ctl keymap bind 106 left-ctrl+c
.venv/bin/akko-ctl keymap bind 106 media:volume-up
.venv/bin/akko-ctl light fill '#00ff00'
.venv/bin/akko-ctl light key 0 '#0000ff'
.venv/bin/akko-ctl light colors
.venv/bin/akko-ctl system status
.venv/bin/akko-ctl system polling 500
.venv/bin/akko-ctl system polling 1000
.venv/bin/akko-ctl system win-lock on
.venv/bin/akko-ctl system win-lock off
.venv/bin/akko-ctl profile save my-keyboard.json
.venv/bin/akko-ctl profile load my-keyboard.json
.venv/bin/akko-ctl profile list
```

Slot numbers are firmware matrix positions, not printed keycodes. On the tested
3098N, Escape is slot 0 and numpad 1 is slot 106. Use `keymap read` to inspect
factory and active assignments. Fn/special slots and empty matrix positions
cannot be rebound. Key targets accept HID key names, modifier names, a modifier
chord, a named media key, or `none`. Media targets are `media:play-pause`,
`media:next`, `media:previous`, `media:stop`, `media:mute`, `media:volume-up`,
and `media:volume-down`. Character output depends on the operating system's
keyboard layout.

Custom colors use the keyboard's own matrix-to-LED map. Per-key changes preserve
other colors and select custom mode 21. Green with blue Escape was physically
confirmed while typing remained functional.

The CLI saves a device backup in `.akko-backups/` before changes such as remaps,
custom color edits, polling changes, and macro uploads. Use `--backup FILE`
where available to select another location. Files are never overwritten.
`keymap backup FILE` saves a device profile, and `keymap restore FILE` restores
only its assignments. Profiles contain active assignments, custom colors,
lighting, Windows-key lock, polling selector, and the USB macro table. They are
local files, not additional onboard profile slots. Restore validates identity,
macro encoding, and all fields before writing. It restores macro data before
reactivating bindings. Unknown macro formats are rejected rather than discarded.
`keymap restore` requires matching macro data when restoring macro bindings;
use `profile load` to restore both together. A timeout stops immediately; use the
saved backup after checking the device state rather than automatically retrying.

The polling command sets and verifies the configured selector
(1000/500/250/125 Hz). Actual USB report timing has not been measured. New
profiles include this setting. Older profiles preserve the current polling rate.

## Onboard macros

```sh
.venv/bin/akko-ctl macro create bc.json b c
.venv/bin/akko-ctl macro upload bc.json
.venv/bin/akko-ctl macro bind 106 0
# Numpad 1 now plays b, then c, once per press.
.venv/bin/akko-ctl macro list
.venv/bin/akko-ctl macro show 0
.venv/bin/akko-ctl macro export keyboard-macros.json
.venv/bin/akko-ctl macro unbind 106
.venv/bin/akko-ctl macro remove 0
```

`create` makes a local JSON file; `upload` replaces the complete USB macro bank.
`bind` assigns a physical matrix slot to a macro index. `unbind` restores that
slot's factory key. To restore a previous custom binding, use its saved backup.
`remove` preserves other indices and refuses to remove a macro that is still
bound. Every live macro mutation backs up the current device first and verifies
readback. Export/create refuse to overwrite existing files.

Each trigger runs the macro once. Use `--repeat COUNT` with `macro create` to
include a bounded number of repetitions in that run. For example,
`macro create example.json left-shift+b mouse:middle --repeat 2` repeats the
chord and middle click twice. Mouse buttons include `mouse:left`, `mouse:right`,
`mouse:middle`, `mouse:back`, and `mouse:forward`. In JSON, use separate
down/up events for each key in a chord. Toggle playback, pointer motion,
and importing legacy ShootData files are unavailable.
`create` accepts key names, not arbitrary text; characters depend on your OS
layout. Edit the exported JSON to build multiple macros or adjust individual
events. Key events use `key`, `action` (`down`/`up`), and `delay_ms` fields.
A wait event has `action: "wait"` and `delay_ms`, without a key. New macros start
with a 100 ms wait and use 100 ms key intervals, the combination confirmed by
repeated physical tests. Upload requires a leading wait of at least 100 ms.
The firmware applies delay **after** an event: increasing the first key's delay
alone did not prevent the first character being dropped. Shorter key intervals
can also be unreliable; the slower defaults prioritize complete output.
Each press must have a release. Delay is 1..10000 ms, total duration at most 60 seconds,
and the whole bank must fit the capacity reported by the keyboard (3072 bytes
on the tested unit).

Replacing the bank temporarily disables macro-bound keys and waits for the
maximum previous macro duration before changing shared playback memory. Ordinary
keys keep working. On a failure, triggers may remain disabled until you restore
the printed backup. No automatic retry is made after an uncertain write.
The tested 3098N retained its key remaps and onboard USB macros after a USB
unplug and reconnect. Wireless playback remains untested.

## Scope

Working hardware features: active key remapping, custom per-key RGB, ordinary
lighting settings/effects, Windows-key lock, configured polling rate, and local device profiles/backups.
Windows-key lock was identified by comparing settings before/after Fn+left Win.

Onboard USB macro playback is now physically confirmed: numpad 1 typed `bc`
with no host daemon. Akko's built-in Fn recorder uses separate native storage;
USB profiles do **not** capture or restore those native recordings.

Legacy JSON helpers operate on separately supplied Akko Windows preset files.
Use `profile save` to capture the current USB configuration of your keyboard.

Firmware flashing is unsupported. The official updater is Windows-only,
requires USB wired mode, and warns that interrupting USB during an update can
brick the keyboard. No firmware or bootloader operations are part of this tool.

See the [USB protocol reference](docs/usb-protocol.md) for report framing, settings,
keymaps, colors, and onboard macro encoding.

## License

[GNU General Public License v3.0 only](LICENSE).
