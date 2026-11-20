"""Clickable ANSI 3098N layout in physical key units and factory matrix slots."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QPushButton

from .desktop_device import Key

# Rows follow Akko's 3098N manual. Matrix slots were read from the USB device.
# Each run starts at x, y and contains (slot, legend[, width[, height]]).
ROWS = (
    (0, 0, ((0, 'Esc'),)),
    (2, 0, ((12, 'F1'), (18, 'F2'), (24, 'F3'), (30, 'F4'))),
    (6.5, 0, ((36, 'F5'), (42, 'F6'), (48, 'F7'), (54, 'F8'))),
    (11, 0, ((60, 'F9'), (66, 'F10'), (72, 'F11'), (78, 'F12'))),
    (15.5, 0, ((86, 'Del'), (85, 'Ins'), (97, 'PgUp'), (98, 'PgDn'))),
    (0, 1.25, ((1, '`'), (7, '1'), (13, '2'), (19, '3'), (25, '4'), (31, '5'),
               (37, '6'), (43, '7'), (49, '8'), (55, '9'), (61, '0'), (67, '-'),
               (73, '='), (79, 'Backspace', 2))),
    (15.5, 1.25, ((103, 'Num'), (109, '/'), (115, '*'), (121, '-'))),
    (0, 2.25, ((2, 'Tab', 1.5), (8, 'Q'), (14, 'W'), (20, 'E'), (26, 'R'), (32, 'T'),
               (38, 'Y'), (44, 'U'), (50, 'I'), (56, 'O'), (62, 'P'), (68, '['),
               (74, ']'), (80, '\\', 1.5))),
    (15.5, 2.25, ((104, '7'), (110, '8'), (116, '9'), (122, '+', 1, 2))),
    (0, 3.25, ((3, 'Caps', 1.75), (9, 'A'), (15, 'S'), (21, 'D'), (27, 'F'), (33, 'G'),
               (39, 'H'), (45, 'J'), (51, 'K'), (57, 'L'), (63, ';'), (69, "'"),
               (81, 'Enter', 2.25))),
    (15.5, 3.25, ((105, '4'), (111, '5'), (117, '6'))),
    (0, 4.25, ((4, 'Shift', 2.25), (16, 'Z'), (22, 'X'), (28, 'C'), (34, 'V'),
               (40, 'B'), (46, 'N'), (52, 'M'), (58, ','), (64, '.'), (70, '/'),
               (82, 'Shift', 1.75))),
    (14.25, 4.5, ((94, '↑'),)),
    (15.5, 4.25, ((106, '1'), (112, '2'), (118, '3'), (124, 'Enter', 1, 2))),
    (0, 5.25, ((5, 'Ctrl', 1.25), (11, 'Super', 1.25), (17, 'Alt', 1.25),
               (41, 'Space', 6.25), (65, 'Alt'), (71, 'Fn'), (83, 'Ctrl'))),
    (13.25, 5.5, ((89, '←'), (95, '↓'), (101, '→'))),
    (16.5, 5.25, ((113, '0'), (119, '.'))),
)

KEY_STYLE = """
QPushButton {
    background: #202e40; color: #edf3fb;
    border: 1px solid #384c64; border-bottom: 3px solid %(color)s;
    border-radius: 5px; padding: 0; font-size: %(font)dpx; font-weight: 600;
}
QPushButton:hover { background: #2d4056; }
QPushButton:checked { background: #275448; border-color: #8be4c8; border-bottom-color: %(color)s; }
QPushButton:focus { outline: none; border-top: 2px solid #e0fff4; }
QPushButton:disabled { background: #192332; color: #8795a6; border-color: #303e50; }
"""


class Keyboard(QFrame):
    selection_changed = Signal()

    def __init__(self):
        super().__init__()
        self.setAccessibleName('3098N virtual keyboard')
        self.setMinimumSize(550, 200)
        self.keys: dict[int, Key] = {}
        self.buttons: dict[int, QPushButton] = {}
        self.positions: dict[int, tuple[float, float, float, float]] = {}
        self._font = 11
        for x, y, row in ROWS:
            for slot, legend, *size in row:
                width, height = (*size, 1, 1)[:2]
                cap = QPushButton(legend, self)
                cap.setCheckable(True)
                cap.setEnabled(False)
                cap.clicked.connect(self.selection_changed)
                cap.setStyleSheet(self._style(slot))
                self.buttons[slot] = cap
                self.positions[slot] = (x, y, width, height)
                x += width

    def set_keys(self, keys: list[Key]):
        self.keys = {key.slot: key for key in keys}
        for slot, cap in self.buttons.items():
            key = self.keys.get(slot)
            cap.setEnabled(key is not None)
            if key is None:
                cap.setChecked(False)
                cap.setToolTip('')
            else:
                cap.setAccessibleName(f'{cap.text()}, slot {slot}')
                details = f'Assignment: {key.assignment}\nCustom color: {key.color or "Unavailable"}'
                cap.setAccessibleDescription(details)
                cap.setToolTip(f'{cap.text()} · Slot {slot}\n{details}')
            cap.setStyleSheet(self._style(slot))
        self.selection_changed.emit()

    def selected_keys(self) -> list[Key]:
        return [self.keys[slot] for slot, cap in self.buttons.items() if cap.isChecked()]

    def clear_selection(self):
        for cap in self.buttons.values():
            cap.setChecked(False)
        self.selection_changed.emit()

    def _style(self, slot):
        key = self.keys.get(slot)
        return KEY_STYLE % {'color': (key.color if key else None) or '#384c64', 'font': self._font}

    def resizeEvent(self, event):
        # Fit roughly square caps to the window while leaving room for the controls.
        unit = min((self.width() - 22) / 19.5, (self.height() - 22) / 6.5)
        left = (self.width() - unit * 19.5) / 2
        top = (self.height() - unit * 6.5) / 2
        gap = 3
        font = max(9, min(13, round(unit * 0.29)))
        for slot, cap in self.buttons.items():
            x, y, width, height = self.positions[slot]
            cap.setGeometry(round(left + x * unit), round(top + y * unit),
                            round(width * unit) - gap, round(height * unit) - gap)
        if font != self._font:
            self._font = font
            for slot, cap in self.buttons.items():
                cap.setStyleSheet(self._style(slot))
        super().resizeEvent(event)
