"""Qt desktop interface for the Akko 3098N."""

from __future__ import annotations

import shlex
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import desktop_device as device
from .desktop_keyboard import Keyboard
from .features import lighting, live_keymap, snapshot, usb_macros
from .features.system import set_polling_rate, set_win_lock
from .protocol import PollingRate

STYLE = """
QWidget { background: #111822; color: #edf3fb; font-size: 14px; }
QFrame#sidebar { background: #0c121b; border-right: 1px solid #253246; }
QFrame#sidebar QLabel, QFrame#sidebar QListWidget { background: transparent; }
QLabel#brand { color: #96f2d3; font-weight: 700; font-size: 13px; }
QLabel#title { font-size: 28px; font-weight: 700; }
QLabel#section { font-size: 21px; font-weight: 650; }
QLabel#muted { color: #a8b7ca; }
QFrame#card { background: #182230; border: 1px solid #29394d; border-radius: 12px; }
QFrame#card QLabel, QFrame#card QCheckBox { background: transparent; }
QPushButton, QLineEdit, QComboBox, QSpinBox, QPlainTextEdit {
    background: #202d3e; border: 1px solid #3a4c63; border-radius: 6px; padding: 7px 10px;
    selection-background-color: #316958;
}
QCheckBox::indicator { width: 16px; height: 16px; border: 1px solid #7890a9;
    border-radius: 4px; background: #111822; }
QCheckBox::indicator:checked { background: #97f2d2; border-color: #97f2d2; }
QPushButton:hover { background: #2b3e54; }
QPushButton#primary { background: #97f2d2; color: #0b2821; font-weight: 700; border-color: #97f2d2; }
QPushButton#primary:hover { background: #baffe8; }
QPushButton:disabled, QPushButton#primary:disabled { background: #1c2736; color: #8492a4; border-color: #314057; }
*:focus { border-color: #97f2d2; }
QListWidget { border: 1px solid #314057; border-radius: 6px;
    background: #151f2d;
    selection-background-color: #265647; selection-color: #f2fff9; }
QListWidget#navigation { border: 0; outline: 0; }
QListWidget::item { padding: 9px; }
QListWidget::item:selected { background: #24483f; color: #b9ffe8; border-radius: 5px; }
QWidget#keyboard { background: #121c28; border: 1px solid #29394d; border-radius: 12px; }
"""


def label(text, role=''):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(role)
    return widget


def button(parent_layout, text, callback, primary=False):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    if primary:
        widget.setObjectName('primary')
    parent_layout.addWidget(widget)
    return widget


def spin(minimum, maximum, value):
    widget = QSpinBox()
    widget.setRange(minimum, maximum)
    widget.setValue(value)
    return widget


def line(placeholder):
    widget = QLineEdit()
    widget.setPlaceholderText(placeholder)
    return widget


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Akko 3098N Control')
        self.resize(1060, 720)
        self.setMinimumSize(820, 620)
        self._pool = ThreadPoolExecutor(max_workers=1)
        self._job = None
        self.state = None
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._finish_job)

        root = QWidget()
        self.setCentralWidget(root)
        frame = QHBoxLayout(root)
        frame.setContentsMargins(0, 0, 0, 0)
        frame.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(180)
        nav_layout = QVBoxLayout(sidebar)
        nav_layout.setContentsMargins(14, 26, 14, 18)
        nav_layout.addWidget(label('AKKO CONTROL', 'brand'))
        self.navigation = QListWidget(objectName='navigation')
        self.navigation.addItems(['Lighting', 'Keymap', 'Macros', 'Profiles', 'System'])
        nav_layout.addSpacing(18)
        nav_layout.addWidget(self.navigation)
        frame.addWidget(sidebar)

        main = QVBoxLayout()
        main.setContentsMargins(26, 22, 26, 18)
        main.setSpacing(14)
        header = QHBoxLayout()
        identity = QVBoxLayout()
        identity.addWidget(label('Akko 3098N', 'title'))
        self.connection = label('Checking USB connection…', 'muted')
        identity.addWidget(self.connection)
        header.addLayout(identity, 1)
        self.refresh_button = button(header, 'Refresh device', self.refresh)
        main.addLayout(header)
        self.pages = QStackedWidget()
        for build in (self._lighting, self._keymap, self._macros, self._profiles, self._system):
            self.pages.addWidget(build())
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        main.addWidget(self.pages, 1)
        self.status = label('', 'muted')
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        main.addWidget(self.status)
        frame.addLayout(main, 1)
        self.pages.setEnabled(False)
        QTimer.singleShot(0, self.refresh)

    def _page(self, title, description):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(label(title, 'section'))
        hint = label(description, 'muted')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        return page, layout

    def _card(self, layout):
        frame = QFrame(objectName='card')
        body = QVBoxLayout(frame)
        body.setContentsMargins(16, 14, 16, 14)
        body.setSpacing(10)
        layout.addWidget(frame)
        return body

    def _lighting(self):
        page, layout = self._page('Lighting', 'Set an effect or paint individual keys from the Keymap tab.')
        card = self._card(layout)
        form = QFormLayout()
        self.effect = QComboBox()
        for mode in lighting.Mode:
            self.effect.addItem(mode.name.replace('_', ' ').title(), int(mode))
        self.color = line('#RRGGBB')
        self.color.setText('#ffffff')
        self.color.setAccessibleName('Effect color')
        swatch = QHBoxLayout()
        swatch.addWidget(self.color)
        self.swatch = button(swatch, 'Pick color…', lambda: self._pick(self.color))
        self.color.textChanged.connect(self._update_swatch)
        self.brightness = spin(0, 4, 4)
        self.speed = spin(0, 4, 2)
        self.multicolor = QCheckBox('Use multicolor')
        for name, widget in [('Effect', self.effect), ('Brightness', self.brightness),
                             ('Speed', self.speed), ('Color', swatch), ('Palette', self.multicolor)]:
            form.addRow(name, widget)
        card.addLayout(form)
        actions = QHBoxLayout()
        button(actions, 'Apply lighting', self._apply_lighting, True)
        button(actions, 'Fill custom colors', self._fill)
        actions.addStretch()
        card.addLayout(actions)
        layout.addStretch()
        return page

    def _keymap(self):
        page, layout = self._page('Keymap', 'Click keys to add or remove them from the selection. '
                                  'The strip on each key shows its saved custom color.')
        self.keyboard = Keyboard()
        self.keyboard.setObjectName('keyboard')
        layout.addWidget(self.keyboard, 1)
        card = self._card(layout)
        selection = QHBoxLayout()
        self.selected_key = label('')
        self.selected_key.setWordWrap(True)
        selection.addWidget(self.selected_key, 1)
        self.clear_keys = button(selection, 'Clear selection', self.keyboard.clear_selection)
        card.addLayout(selection)
        row = QHBoxLayout()
        self.target = line('e.g. b, left-ctrl+c, media:mute')
        self.target.setAccessibleName('New assignment')
        self.target.returnPressed.connect(self._bind_key)
        row.addWidget(self.target, 1)
        self.apply_key = button(row, 'Apply remap', self._bind_key, True)
        self.reset_key = button(row, 'Restore factory', self._reset_key)
        self.paint_key = button(row, 'Set color…', self._paint)
        card.addLayout(row)
        self.keyboard.selection_changed.connect(self._key_selected)
        self._key_selected()
        return page

    def _macros(self):
        page, layout = self._page('Onboard macros', 'Create a sequence and bind it to a key. The keyboard plays it on its own.')
        row = QHBoxLayout()
        self.macros = QListWidget()
        self.macros.setAccessibleName('Onboard macro slots')
        self.macros.currentRowChanged.connect(self._macro_selected)
        row.addWidget(self.macros, 1)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setAccessibleName('Selected macro events')
        row.addWidget(self.preview, 2)
        layout.addLayout(row, 1)
        card = self._card(layout)
        form = QFormLayout()
        self.sequence = line('e.g. left-shift+b c mouse:middle')
        self.repeat = spin(1, 255, 1)
        self.delay = spin(1, 10000, 100)
        self.delay.setSuffix(' ms')
        self.macro_key = QComboBox()
        self.macro_key.setPlaceholderText('Choose a trigger key')
        for name, widget in [('Sequence', self.sequence), ('Repeat count', self.repeat),
                             ('Event delay', self.delay), ('Trigger key', self.macro_key)]:
            form.addRow(name, widget)
        card.addLayout(form)
        actions = QHBoxLayout()
        self.add_macro = button(actions, 'Add macro', self._add_macro, True)
        self.bind_macro = button(actions, 'Bind selected', self._bind_macro)
        self.remove_macro = button(actions, 'Remove selected', self._remove_macro)
        self.export_macros = button(actions, 'Export bank…', self._export_macros)
        self.import_macros = button(actions, 'Import bank…', self._import_macros)
        card.addLayout(actions)
        self.macro_key.currentIndexChanged.connect(self._macro_selected)
        return page

    def _profiles(self):
        page, layout = self._page('Profiles', 'Save or restore a complete USB profile as a JSON file.')
        card = self._card(layout)
        actions = QHBoxLayout()
        button(actions, 'Save profile…', self._save_profile, True)
        button(actions, 'Load profile…', self._load_profile)
        actions.addStretch()
        card.addLayout(actions)
        info = label(f'Automatic backups\n{device.backup_directory()}', 'muted')
        info.setWordWrap(True)
        info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        card.addWidget(info)
        layout.addStretch()
        return page

    def _system(self):
        page, layout = self._page('System', 'Manage the Windows-key lock and the configured USB polling rate.')
        card = self._card(layout)
        form = QFormLayout()
        self.win_lock = QCheckBox('Lock the Windows key')
        self.polling = QComboBox()
        for rate in sorted(PollingRate, key=lambda rate: int(rate.name[3:])):
            self.polling.addItem(f'{rate.name[3:]} Hz', int(rate))
        form.addRow('Windows key', self.win_lock)
        form.addRow('Polling rate', self.polling)
        card.addLayout(form)
        actions = QHBoxLayout()
        button(actions, 'Apply Windows-key setting', self._apply_win, True)
        button(actions, 'Apply polling rate', self._apply_polling)
        actions.addStretch()
        card.addLayout(actions)
        layout.addStretch()
        return page

    def _submit(self, message, work, callback, device_io=True):
        if self._job is not None:
            return
        self._job = self._pool.submit(work), callback, device_io
        self._timer.start()
        self.status.setText(message)
        self.pages.setEnabled(False)
        self.refresh_button.setEnabled(False)

    def _finish_job(self):
        future, callback, device_io = self._job
        if not future.done():
            return
        self._timer.stop()
        self._job = None
        try:
            callback(future.result())
        except (ValueError, OSError, RuntimeError) as exc:
            if device_io:
                self.state = None
                self.connection.setText('Device state unavailable')
            self.status.setText(str(exc))
        finally:
            if self._job is None:
                self.pages.setEnabled(self.state is not None)
                self.refresh_button.setEnabled(True)

    def refresh(self, note=''):
        self._submit('Reading keyboard…', device.read_state, partial(self._render, note=note or ''))

    def _change(self, operation):
        self._submit('Saving backup and applying changes…', partial(device.change_device, operation),
                     lambda backup: self.refresh(f'Applied and verified. Backup saved to {backup}'))

    def _render(self, state, note):
        self.state = state
        self.connection.setText(f'Connected over USB  ·  {state.path}')
        cfg = state.config
        self.effect.setCurrentIndex(self.effect.findData(int(cfg.mode)))
        self.brightness.setValue(int(cfg.brightness))
        self.speed.setValue(int(cfg.speed))
        self.color.setText(cfg.color.to_hex())
        self.multicolor.setChecked(cfg.random_flag)
        self.win_lock.setChecked(not state.windows_enabled)
        self.polling.setCurrentIndex(self.polling.findData(int(state.rate)))
        self.keyboard.set_keys(state.keys)
        index = self.macros.currentRow()
        self.macros.clear()
        selected_slot = self.macro_key.currentData()
        self.macro_key.clear()
        for key in state.keys:
            if key.factory.kind == 0x20:
                self.macro_key.addItem(f'{key.factory.describe()} · slot {key.slot}', key.slot)
        self.macro_key.setCurrentIndex(self.macro_key.findData(selected_slot))
        for number, events in enumerate(state.macros or [], 1):
            self.macros.addItem(f'Macro {number} · {len(events)} events' if events else f'Macro {number} · Empty')
        if self.macros.count():
            self.macros.setCurrentRow(max(0, min(index, self.macros.count() - 1)))
        self._macro_selected()
        self.status.setText(note or 'Settings read from keyboard.')

    def _key_selected(self):
        keys = self.keyboard.selected_keys()
        editable = bool(keys) and all(key.factory.kind == 0x20 for key in keys)
        paintable = bool(keys) and all(key.color is not None for key in keys)
        message = 'No keys selected'
        if len(keys) == 1:
            key = keys[0]
            legend = self.keyboard.buttons[key.slot].text()
            message = f'{legend}  →  {key.assignment}  ·  {key.color or "No custom color"}'
        elif keys:
            message = f'{len(keys)} keys selected'
        if keys and not editable:
            message += '  ·  Selection includes a protected key'
        self.selected_key.setText(message)
        self.clear_keys.setEnabled(bool(keys))
        self.target.setEnabled(editable)
        self.apply_key.setEnabled(editable)
        self.reset_key.setEnabled(editable)
        self.paint_key.setEnabled(paintable)
        self.paint_key.setToolTip('Every selected key needs an addressable LED.' if keys and not paintable else '')

    def _bind_key(self):
        if self.apply_key.isEnabled():
            try:
                target = live_keymap.parse_target(self.target.text().strip())
            except ValueError as exc:
                self.status.setText(str(exc))
                return
            targets = {key.slot: target for key in self.keyboard.selected_keys()}
            self._change(partial(live_keymap.rebind_keys, targets=targets))

    def _reset_key(self):
        targets = {key.slot: None for key in self.keyboard.selected_keys()}
        self._change(partial(live_keymap.rebind_keys, targets=targets))

    def _paint(self):
        keys = self.keyboard.selected_keys()
        colors = {key.color for key in keys}
        initial = next(iter(colors)) if len(colors) == 1 else self.color.text()
        color = QColorDialog.getColor(QColor(initial or '#ffffff'), self, 'Selected key color')
        if color.isValid():
            self._change(partial(lighting.set_key_colors, slots=tuple(key.slot for key in keys),
                                 color=lighting.ColorRGB.from_hex(color.name())))

    def _update_swatch(self, value):
        try:
            color = lighting.ColorRGB.from_hex(value)
        except ValueError:
            self.swatch.setStyleSheet('')
            return
        ink = '#0c1720' if QColor(color.to_hex()).lightnessF() > 0.55 else '#ffffff'
        self.swatch.setStyleSheet(f'background: {color.to_hex()}; color: {ink}; border-color: #748397;')

    def _pick(self, entry):
        color = QColorDialog.getColor(QColor(entry.text()), self, 'Lighting color')
        if color.isValid():
            entry.setText(color.name())

    def _color(self):
        try:
            return lighting.ColorRGB.from_hex(self.color.text().strip())
        except ValueError:
            self.status.setText('Enter a six-digit RGB color such as #97f2d2.')
            return None

    def _apply_lighting(self):
        if color := self._color():
            cfg = lighting.LightingConfig(self.effect.currentData(), self.brightness.value(),
                                          self.speed.value(), self.multicolor.isChecked(), color)
            self._change(partial(lighting.apply, cfg=cfg))

    def _fill(self):
        if color := self._color():
            self._change(partial(device.fill_color, color=color))

    def _macro_selected(self):
        bank = self.state.macros if self.state else None
        index = self.macros.currentRow()
        events = bank[index] if bank and 0 <= index < len(bank) else []
        self.add_macro.setEnabled(bank is not None)
        self.export_macros.setEnabled(bank is not None)
        self.import_macros.setEnabled(bank is not None)
        self.bind_macro.setEnabled(bool(events) and self.macro_key.currentData() is not None)
        self.remove_macro.setEnabled(bool(events))
        if events:
            rows = usb_macros.export([events])['macros'][0]['events']
            self.preview.setPlainText('\n'.join(f"{row['action']:5} {row.get('key', ''):16} {row['delay_ms']} ms"
                                                for row in rows))
        else:
            message = 'Select a macro to see its events.' if bank else 'No onboard USB macros.'
            self.preview.setPlainText(self.state.macro_error if self.state and self.state.macro_error else message)

    def _add_macro(self):
        try:
            events = usb_macros.sequence(shlex.split(self.sequence.text()), self.delay.value(),
                                         self.repeat.value())
        except ValueError as exc:
            self.status.setText(str(exc))
            return
        self._change(partial(device.change_macro, index=None, events=events))

    def _bind_macro(self):
        self._change(partial(usb_macros.bind, slot=self.macro_key.currentData(), index=self.macros.currentRow()))

    def _remove_macro(self):
        index = self.macros.currentRow()
        if QMessageBox.question(self, 'Remove macro', f'Remove macro {index + 1}?') == QMessageBox.StandardButton.Yes:
            self._change(partial(device.change_macro, index=index, events=[]))

    def _export_macros(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Export macro bank', 'macros.json', 'JSON files (*.json)')
        if path and self.state and self.state.macros is not None:
            data = usb_macros.export(self.state.macros)
            self._submit('Exporting macros…', partial(snapshot.save, data, path),
                         lambda saved: self.status.setText(f'Saved {saved}'), device_io=False)

    def _import_macros(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import macro bank', '', 'JSON files (*.json)')
        if path and QMessageBox.question(self, 'Replace macro bank',
                                        'Replace the keyboard’s USB macro bank with this file?') == QMessageBox.StandardButton.Yes:
            def upload(dev):
                usb_macros.upload(dev, usb_macros.parse(snapshot.load(path)))
            self._change(upload)

    def _save_profile(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save keyboard profile', '3098n.json', 'JSON files (*.json)')
        if path:
            self._submit('Saving profile…', partial(device.save_profile, path),
                         lambda saved: self.status.setText(f'Saved {saved}'), device_io=False)

    def _load_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Load keyboard profile', '', 'JSON files (*.json)')
        if path and QMessageBox.question(self, 'Apply profile',
                                        f'Apply {Path(path).name} to the keyboard?') == QMessageBox.StandardButton.Yes:
            self._change(partial(device.load_profile, path=path))

    def _apply_win(self):
        self._change(partial(set_win_lock, locked=self.win_lock.isChecked()))

    def _apply_polling(self):
        self._change(partial(set_polling_rate, rate=PollingRate(self.polling.currentData())))

    def closeEvent(self, event):
        if self._job is not None:
            self.status.setText('Wait for the current operation before closing.')
            event.ignore()
        else:
            self._pool.shutdown(wait=False)
            super().closeEvent(event)


def run():
    app = QApplication(sys.argv[:1])
    app.setApplicationName('Akko 3098N Control')
    app.setStyle('Fusion')
    app.setFont(QFont('Sans Serif', 10))
    app.setStyleSheet(STYLE)
    window = Window()
    window.show()
    return app.exec()
