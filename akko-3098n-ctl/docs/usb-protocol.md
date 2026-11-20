# Akko 3098N USB protocol

This reference describes wired USB behavior observed on the Akko 3098N
(`320f:506a`, product string `AKKO Multi-modes Keyboard-N`). Other Akko models
and firmware revisions may use different layouts. All offsets are zero-based.
Hexadecimal values use the `0x` prefix or appear in hex byte sequences.

## Interface and transport

Use the vendor HID collection on USB interface 1, usage page `0xff1c`, usage
`0x0092`. Open its Linux `/dev/hidraw*` node and exchange numbered input/output
reports with ID `0x04`. Reports are 64 bytes including the ID. If a HID library
handles the report ID separately, supply the 63-byte payload after the ID.

Interface 1 also has input reports for keyboard (ID 1), system (ID 2), consumer
controls (ID 3), and mouse (ID 5). Ignore these on the vendor channel. Keep the
kernel driver attached and leave input ownership with the OS. The application
uses an advisory lock on the hidraw node and keeps one vendor request in flight.

| Wire offset | Length | Meaning |
| --- | ---: | --- |
| 0 | 1 | Report ID `0x04` |
| 1–2 | 2 | Unsigned sum of request bytes 3–63, little-endian |
| 3 | 1 | Command |
| 4 | 1 | Number of data bytes, up to 24 per request |
| 5–6 | 2 | Byte offset into the command's region, little-endian |
| 7 | 1 | Zero in requests. Status in replies, with zero indicating success |
| 8 onward | Variable | Write data in requests or returned data in read replies |

Zero-fill unused request bytes. Read requests carry the requested length and
zero data. Replies echo request bytes 1–6, including the original checksum
even when returned data differs. Validate the report ID, length, echoed fields,
and status. A nonzero status, missing reply, or mismatched reply indicates
failure. Verify writes by reading back the affected bytes. If a write times out,
read the current state before attempting recovery because the write may already
have reached the keyboard.

The 3098N uses direct reads and writes without a transfer session. BEGIN and
END (`0x01` and `0x02`) return status `0xff` on the tested unit.

## Commands and regions

| Read | Write | Region | Length |
| --- | --- | --- | --- |
| `0x03` | — | Device information, beginning at offset 0 | 34 bytes |
| `0x05` | `0x06` | Settings | First 256 bytes readable. Writes limited to the fields below |
| `0x07` | — | Factory assignments | 3 bytes per matrix slot |
| `0x08` | `0x09` | Active assignments | 3 bytes per matrix slot |
| `0x0a` | `0x0b` | Custom colors | 3 bytes per LED entry, with one entry allocated per matrix slot |
| `0x14` | `0x15` | USB macro bank | Capacity from device information |
| `0x1b` | — | Matrix-slot to LED-index map | 1 byte per matrix slot |

Read device information in chunks starting at offsets 0 and 24. Its first two
bytes are `aa 55`. Byte 5 gives the number of matrix slots (170 on the tested
unit). Byte 6 gives macro capacity in units of 128 bytes (24 × 128 = 3072 bytes
on the tested unit). Table sizes include unused slots.

## Lighting and system settings

The active lighting record occupies settings offsets 0–20. Read it, change
only the intended fields, write all 21 bytes at offset 0, then verify by
reading it back. Preserve offsets 0, 4, and 9–20 exactly.

| Record offset | Field | Encoding |
| --- | --- | --- |
| 1 | Effect | Static 1, breathing 3, wave 18, off 20, custom 21. See [Mode](../akko_ctl/protocol.py) for all values |
| 2 | Brightness | 0–4, from off to brightest |
| 3 | Animation interval | `4 - speed`. User speeds 0–4 go from slowest to fastest |
| 5 | Palette | 0 for fixed color, 1 for multicolor |
| 6–8 | Fixed color | Red, green, blue, one byte each |

Some effects ignore palette or speed. Custom mode uses the custom color table.

A request to read all 21 lighting bytes starts with
`04 1a 00 05 15 00 00 00`, followed by 56 zero bytes. A verified static red
write had the following full wire report. The reserved values came from the
keyboard's original record. Always start with the record from your own device.

```text
04 22 02 06 15 00 00 00 00 01 03 01 00 00 ff 00
00 04 00 00 00 00 00 00 00 00 00 00 ff 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00
```

Update system fields independently with size 1 and verify each with `0x05`.

| Settings offset | Field | Encoding |
| --- | --- | --- |
| 21 | Windows key | 0 locked, 1 enabled |
| 22 | Configured polling selector | 0 = 1000 Hz, 1 = 500 Hz, 2 = 250 Hz, 3 = 125 Hz |

Polling selector readback was verified. Actual polling intervals were not measured.

## Assignments and custom colors

Assignment entries are three bytes at offset `slot * 3`. Read factory and
active entries separately. A zero factory entry marks an unused slot. Preserve
factory special-function entries such as Fn.

| Tag | Byte 1 | Byte 2 |
| --- | --- | --- |
| `0x20` keyboard | USB modifier bitmask, bit 0 through 7 for usages `0xe0`–`0xe7` | Keyboard HID usage, or 0 for a modifier-only binding |
| `0x30` consumer | Low byte of consumer usage | High byte of consumer usage |
| `0x70` one-shot macro | Zero-based macro index | 0 |

`20 00 00` disables a key. `20 00 05` maps to B and `30 e9 00` maps to volume
up. Numpad 1 is slot 106 (byte offset 318) on the tested unit. The Fn layer uses
separate firmware tables. No write protocol for those tables has been verified.

To recolor a key, look up its slot in the LED map. The corresponding RGB entry
begins at `led_index * 3`; `0xff` means no addressable LED. Apply updates to
the existing table, upload the full table in chunks, and compare readback before
selecting custom effect 21. Several keys can be updated in the same table upload.

## USB macro bank

The entire empty bank is zero-filled. A populated bank begins with a 16-byte
header, a table of little-endian 16-bit record offsets, then consecutive macro
records. Offsets are relative to the beginning of the bank.

| Header offset | Length | Meaning |
| --- | ---: | --- |
| 0 | 2 | Magic bytes `aa 55` |
| 2 | 2 | Total used length including the header, offsets, and records |
| 4 | 2 | Macro count, 1–256 |
| 6 | 10 | Reserved, zeros |
| 16 | 2 × count | Record offsets |

Each record starts with a little-endian 16-bit event count and two reserved zero
bytes. Events follow at record offset 4. Each event is four bytes: delay in
milliseconds (little-endian 16-bit), event type, and event argument.

| Base type | Argument | Action |
| --- | --- | --- |
| `0x00` | 0 | Wait |
| `0x01` | Mouse button mask. Bits 0–4 are left, right, middle, back, forward | Button press/release |
| `0x09` | Single modifier bit for HID usage `0xe0`–`0xe7` | Modifier press/release |
| `0x0a` | Ordinary keyboard HID usage `0x04`–`0x93` | Rollover key press/release |

Set bit 7 of the type for press and clear it for release. Delay runs after the
event. A separate initial wait of at least 100 ms prevents intermittent missing
first characters observed during testing. Ordinary keystrokes use the rollover
path (`0x0a`), and type `0x09` is reserved here for modifier masks.

This is the used portion of a one-record bank that types B then C. It contains a
100 ms lead-in and 100 ms between events. Pad the remainder with zeros up to the
device's reported capacity.

```text
aa 55 2a 00 01 00 00 00 00 00 00 00 00 00 00 00
12 00 05 00 00 00 64 00 00 00 64 00 8a 05 64 00
0a 05 64 00 8a 06 64 00 0a 06
```

Before replacing playback memory, temporarily disable active macro triggers and
wait for any in-flight playback to finish. Write the full bank in 24-byte chunks.
The tested firmware can skip a change confined to header bytes when writing at
offset 0. If readback differs at bytes 1–15, write those 15 bytes at offset 1.
Verify the entire bank before restoring bindings. A failure can leave triggers
disabled. The tool saves a profile before macro changes for recovery.

The build supports one-shot bindings and finite repetition encoded as repeated
events. Native Fn-recorded macros use separate storage and are outside USB
profiles. Toggle playback, pointer motion, wireless setup, and firmware
flashing are outside the supported protocol.
