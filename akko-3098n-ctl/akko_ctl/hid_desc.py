"""3098N identity and report constants, verified against Linux sysfs.

Interface 1 includes keyboard report 1 (modifier bits and a rollover bitmap),
system report 2, consumer report 3, vendor report 4 (63-byte input/output payload),
and mouse report 5. Report 4 is the settings channel; do not apply Sonix or
generic EVision packet layouts to this device. See docs/usb-protocol.md.
"""

VENDOR_USAGE_PAGE = 0xFF1C
VENDOR_USAGE = 0x0092
VENDOR_REPORT_ID = 0x04
VENDOR_PAYLOAD_LEN = 63          # bytes after the report-ID byte
VENDOR_REPORT_LEN = 64           # total HID report size on the wire

VID = 0x320F
PID = 0x506A

__all__ = [
    "PID",
    "VENDOR_PAYLOAD_LEN",
    "VENDOR_REPORT_ID",
    "VENDOR_REPORT_LEN",
    "VENDOR_USAGE",
    "VENDOR_USAGE_PAGE",
    "VID",
]
