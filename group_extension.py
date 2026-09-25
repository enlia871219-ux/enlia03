# -*- coding: utf-8 -*-
"""Macro-group UI/playback extension for ShadeLawcro.

This module is installed by main.py and patches the existing MainWindow without
changing the proven image-recognition/playback implementation in lawcro_core.py.
"""
from __future__ import annotations
import json, threading, time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox, QListWidget,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QRadioButton,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox, QFileDialog, QMessageBox,
    QDialog, QDialogButtonBox, QLineEdit, QAbstractItemView, QHeaderView
)


def install(core):
    """Patch the imported core.MainWindow class."""
    Group = core.Group
    Step = core.Step
    Signals = core.Signals
    MacroWorker = core.MacroWorker
    now = core.now
    APP_DIR = core.APP_DIR
    DATA_DIR = core.DATA_DIR
    find_window_by_title = core.find_window_by_title
    window_process_name = core.window_process_name

    @dataclass
    class GroupEntry:
        name: str
        chains: list[dict] = field(default_factory=list)
        settings: dict = field(default_factory=dict)

    def default_settings():
        return {
            'mode': 'infinite', 'repeat': 1, 'minutes': 10.0,
            'cycle_wait': 0.0, 'speed': 1.0, 'default_acc': 0.80,
            'background': False, 'target_title': '', 'target_process': '',
            'target_hwnd': None,
        }

    def norm_chain(value):
        if isinstance(value, str):
            return {'path': value, 'wait': 0.0}
        if isinstance(value, dict):
            return {'path': str(value.get('path', '')), 'wait': float(value.get('wait', 0.0) or 0.0)}
        return {'path': '', 'wait': 0.0}

    def groups_path(self):
        return DATA_DIR / 'groups.json'

    def load_groups(self):
        try:
            raw = json.loads(groups_path(self).read_text(encoding='utf-8'))
            self.groups = []
            for item in raw if isinstance(raw, list) else []:
                if not isinstance(item, dict):
                    continue
                settings = default_settings(); settings.update(item.get('settings') or {})
                chains = [norm_chain(x) for x in item.get('chains', []) or []]
                self.groups.append(GroupEntry(str(item.get('name') or '새 매크로 그룹 1'), chains, settings))
        except Exception:
            self.groups = []

    def save_groups(self):
        payload = []
        for g in self.groups:
            payload.append({'name': g.name, 'chains': [norm_chain(x) for x in g.chains], 'settings': dict(g.settings or {})})
        try:
            groups_path(self).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception:
            pass

    def unique_group_name(self):
        used = {g.name for g in self.groups}
        n = 1
        while f'새 매크로 그룹 {n}' in used:
            n += 1
        return f'새 매크로 그룹 {n}'

    def add_group(self):
        self.groups.append(GroupEntry(unique_group_name(self), [], default_settings()))
        self.save_groups(); self.refresh_groups()
        self.group_list.setCurrentRow(len(self.groups) - 1)
        self.refresh_group_chains()

    def rename_group(self):
        i = self.group_list.currentRow()
        if i < 0:
            return
        dlg = QDialog(self); dlg.setWindowTitle('그룹 이름 변경')
        lay = QVBoxLayout(dlg); edit = QLineEdit(self.groups[i].name); lay.addWidget(edit)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        lay.addWidget(buttons); buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject)
        if dlg.exec() == QDialog.Accepted and edit.text().strip():
            self.groups[i].name = edit.text().strip(); self.save_groups(); self.refresh_groups(); self.group_list.setCurrentRow(i)

    def delete_group(self):
        i = self.group_list.currentRow()
        if i < 0:
            return
        name = self.groups[i].name
        answer = QMessageBox.question(self, '그룹 삭제', f'그룹 "{name}"을(를) 삭제하겠습니까?', QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer == QMessageBox.Yes:
            self.groups.pop(i); self.save_groups(); self.refresh_groups()

    def group_event_filter(self, obj, event):
        if obj is getattr(self, 'group_list', None) and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete:
            self.delete_group(); return True
        return super(type(self), self).eventFilter(obj, event)

    def refresh_groups(self):
        old = self.group_list.currentRow()
        self.group_list.blockSignals(True); self.group_list.clear()
        self.group_list.addItems([g.name for g in self.groups]); self.group_list.blockSignals(False)
        if self.groups:
            self.group_list.setCurrentRow(min(max(old, 0), len(self.groups) - 1))
        else:
            self.group_chain_table.setRowCount(0)
        self.refresh_group_chains()

    def refresh_group_chains(self):
        self.group_chain_table.setRowCount(0)
        i = self.group_list.currentRow()
        if i < 0 or i >= len(self.groups):
            self._load_group_settings(default_settings())
            return
        g = self.groups[i]
        self.group_chain_table.setRowCount(len(g.chains))
        for r, raw in enumerate(g.chains):
            c = norm_chain(raw); g.chains[r] = c
            vals = (str(r + 1), Path(c['path']).name if c['path'] else '(체인 없음)', f"{c['wait']:.1f}초")
            for col, val in enumerate(vals):
                self.group_chain_table.setItem(r, col, QTableWidgetItem(val))
        self._highlight_group_chain(-1)
        self._load_group_settings(g.settings)

    def _highlight_group_chain(self, index):
        for r in range(self.group_chain_table.rowCount()):
            bg = QColor('#dbeafe') if r == index else QColor('#ffffff' if r % 2 == 0 else '#f7faff')
            for c in range(self.group_chain_table.columnCount()):
                item = self.group_chain_table.item(r, c)
                if item: item.setBackground(bg)
        if 0 <= index < self.group_chain_table.rowCount():
            self.group_chain_table.selectRow(index)

    def add_chain_to_group(self):
        gi = self.group_list.currentRow()
        if gi < 0: return
        files, _ = QFileDialog.getOpenFileNames(self, '체인 불러오기', str(APP_DIR), 'PChain (*.pchain *.json)')
        if files:
            self.groups[gi].chains.extend({'path': f, 'wait': 0.0} for f in files)
            self.save_groups(); self.refresh_group_chains()

    def remove_chain_from_group(self):
        gi = self.group_list.currentRow(); ci = self.group_chain_table.currentRow()
        if gi >= 0 and ci >= 0:
            self.groups[gi].chains.pop(ci); self.save_groups(); self.refresh_group_chains()

    def edit_group_chain(self):
        gi = self.group_list.currentRow(); ci = self.group_chain_table.currentRow()
        if gi < 0 or ci < 0: return
        c = norm_chain(self.groups[gi].chains[ci])
        dlg = QDialog(self); dlg.setWindowTitle('그룹 체인 편집')
        form = QFormLayout(dlg)
        wait = QDoubleSpinBox(); wait.setRange(0, 3600); wait.setDecimals(1); wait.setSingleStep(.1); wait.setValue(c['wait'])
        form.addRow('체인 실행 후 대기 시간(초)', wait); form.addRow('체인 이름', QLabel(Path(c['path']).name))
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        form.addRow(buttons); buttons.accepted.connect(dlg.accept); buttons.rejected.connect(dlg.reject)
        if dlg.exec() == QDialog.Accepted:
            self.groups[gi].chains[ci] = {'path': c['path'], 'wait': wait.value()}
            self.save_groups(); self.refresh_group_chains(); self.group_chain_table.selectRow(ci)

    def move_group_chain_up(self):
        gi = self.group_list.currentRow(); ci = self.group_chain_table.currentRow()
        if gi >= 0 and ci > 0:
            chains = self.groups[gi].chains; chains[ci - 1], chains[ci] = chains[ci], chains[ci - 1]
            self.save_groups(); self.refresh_group_chains(); self.group_chain_table.selectRow(ci - 1)

    def move_group_chain_down(self):
        gi = self.group_list.currentRow(); ci = self.group_chain_table.currentRow()
        if gi >= 0 and 0 <= ci < len(self.groups[gi].chains) - 1:
            chains = self.groups[gi].chains; chains[ci + 1], chains[ci] = chains[ci], chains[ci + 1]
            self.save_groups(); self.refresh_group_chains(); self.group_chain_table.selectRow(ci + 1)

    def export_group(self):
        gi = self.group_list.currentRow()
        if gi < 0: return
        g = self.groups[gi]
        path, _ = QFileDialog.getSaveFileName(self, '그룹 저장', str(APP_DIR / f'{g.name}.gchain'), 'GChain (*.gchain)')
        if not path: return
        if not path.lower().endswith('.gchain'): path += '.gchain'
        data = {'version': '1.0', 'name': g.name, 'chains': [norm_chain(x) for x in g.chains], 'settings': dict(g.settings or {})}
        Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def import_group(self):
        path, _ = QFileDialog.getOpenFileName(self, '그룹 불러오기', str(APP_DIR), 'GChain (*.gchain)')
        if not path: return
        try:
            data = json.loads(Path(path).read_text(encoding='utf-8'))
            settings = default_settings(); settings.update(data.get('settings') or {})
            self.groups.append(GroupEntry(str(data.get('name') or Path(path).stem), [norm_chain(x) for x in data.get('chains', [])], settings))
            self.save_groups(); self.refresh_groups(); self.group_list.setCurrentRow(len(self.groups) - 1)
        except Exception as e:
            QMessageBox.critical(self, '그룹 불러오기 실패', f'{type(e).__name__}: {e}')

    def _group_settings_changed(self, *_):
        if getattr(self, '_loading_group_settings', False): return
        gi = self.group_list.currentRow()
        if gi < 0: return
        mode = 'count' if self.g_count.isChecked() else 'time' if self.g_time.isChecked() else 'infinite'
        self.groups[gi].settings = {
            'mode': mode, 'repeat': self.g_repeat.value(), 'minutes': self.g_minutes.value(),
            'cycle_wait': self.g_cycle_wait.value(), 'speed': float(self.g_speed.currentText().replace('x', '')),
            'default_acc': self.g_default_acc.value(), 'background': self.g_background.isChecked(),
            'target_title': self.g_target_title.text().strip(), 'target_process': self.g_target_process.text().strip(),
            'target_hwnd': getattr(self, '_group_target_hwnd', None),
        }
        self.save_groups()

    def _load_group_settings(self, raw):
        s = default_settings(); s.update(raw or {})
        self._loading_group_settings = True
        try:
            mode = s['mode']; self.g_inf.setChecked(mode == 'infinite'); self.g_count.setChecked(mode == 'count'); self.g_time.setChecked(mode == 'time')
            self.g_repeat.setValue(int(s['repeat'])); self.g_minutes.setValue(float(s['minutes'])); self.g_cycle_wait.setValue(float(s['cycle_wait']))
            self.g_speed.setCurrentText(f"{float(s['speed']):.1f}x"); self.g_default_acc.setValue(float(s['default_acc']))
            self.g_background.setChecked(bool(s['background'])); self.g_target_title.setText(str(s['target_title'])); self.g_target_process.setText(str(s['target_process']))
            try: self._group_target_hwnd = int(s.get('target_hwnd') or 0) or None
            except Exception: self._group_target_hwnd = None
            if self._group_target_hwnd:
                self.g_target_status.setText(f"✓ 선택됨: {self.g_target_title.text()}  [{self.g_target_process.text()}]")
            else:
                self.g_target_status.setText('대상 창: 아직 선택되지 않음')
        finally:
            self._loading_group_settings = False
        self._update_group_repeat_controls()

    def _update_group_repeat_controls(self):
        self.g_repeat.setEnabled(self.g_count.isChecked()); self.g_minutes.setEnabled(self.g_time.isChecked())

    def select_group_target(self):
        # Reuse the proven window picker from the chain tab, then copy its result.
        self.select_target_window()
        hwnd = getattr(self, '_last_target_hwnd', None)
        if hwnd:
            self._group_target_hwnd = int(hwnd); self.g_target_title.setText(self.foreground_window_title_for(hwnd)); self.g_target_process.setText(window_process_name(hwnd))
            self.g_target_status.setText(f"✓ 선택됨: {self.g_target_title.text()}  [{self.g_target_process.text()}]"); self._group_settings_changed()

    def current_group_target(self):
        hwnd = getattr(self, '_group_target_hwnd', None)
        title = self.g_target_title.text().strip(); proc = self.g_target_process.text().strip()
        if hwnd and core.ctypes.windll.user32.IsWindow(hwnd): return int(hwnd)
        return find_window_by_title(title, proc)

    def start_group_play(self):
        if getattr(self, 'group_playing', False) or self.playing or self.recording: return
        gi = self.group_list.currentRow()
        if gi < 0 or not self.groups[gi].chains:
            QMessageBox.information(self, '그룹 재생', '재생할 매크로 체인이 없습니다.'); return
        g = self.groups[gi]; settings = default_settings(); settings.update(g.settings or {})
        if settings['background']:
            hwnd = self.current_group_target()
            if not hwnd:
                QMessageBox.warning(self, '그룹 백그라운드 재생', '선택된 대상 창을 찾지 못했습니다.'); return
            settings['target_hwnd'] = int(hwnd)
        start = self.group_chain_table.currentRow()
        if start < 0: start = 0
        self._group_signals = Signals(); self._group_worker = GroupWorker(self, g.chains, settings, start, self._group_signals)
        self.group_playing = True; self.group_paused = False; self._highlight_group_chain(start)
        self._group_signals.run.connect(self.runlog); self._group_signals.status.connect(self._highlight_group_chain); self._group_signals.finished.connect(self._group_finished)
        self.update_button_states(); self._group_worker.start()

    def stop_group_play(self):
        worker = getattr(self, '_group_worker', None)
        if worker: worker.stop()
        self.group_playing = False; self.group_paused = False; self.update_button_states()

    def toggle_group_pause(self):
        worker = getattr(self, '_group_worker', None)
        if not worker or not worker.is_alive(): return
        if self.group_paused: worker.resume(); self.group_paused = False
        else: worker.pause(); self.group_paused = True
        self.g_pause_btn.setText('재개 (Shift+F5)' if self.group_paused else '일시 정지 (Shift+F5)'); self.update_button_states()

    def _group_finished(self):
        self.group_playing = False; self.group_paused = False; self.g_pause_btn.setText('일시 정지 (Shift+F5)'); self._highlight_group_chain(-1); self.update_button_states()

    def update_group_button_states(self):
        if not hasattr(self, 'g_start_btn'): return
        busy = bool(self.group_playing or self.playing or self.recording)
        self.g_start_btn.setEnabled(not busy); self.g_pause_btn.setEnabled(self.group_playing); self.g_stop_btn.setEnabled(self.group_playing)
        for b in (self.g_start_btn, self.g_pause_btn, self.g_stop_btn):
            self.style().unpolish(b); self.style().polish(b); b.update()

    def group_tab(self):
        page = QWidget(); root = QVBoxLayout(page)
        top = QHBoxLayout(); title = QLabel('ShadeLawcro V1.0 매크로 그룹'); title.setObjectName('title'); top.addWidget(title); top.addStretch()
        self.g_start_btn = QPushButton('재생 시작 (Shift+F3)'); self.g_pause_btn = QPushButton('일시 정지 (Shift+F5)'); self.g_stop_btn = QPushButton('재생 중지 (Shift+F4)')
        self.g_start_btn.clicked.connect(self.start_group_play); self.g_pause_btn.clicked.connect(self.toggle_group_pause); self.g_stop_btn.clicked.connect(self.stop_group_play)
        for b in (self.g_start_btn, self.g_pause_btn, self.g_stop_btn): b.setMinimumHeight(36); top.addWidget(b)
        root.addLayout(top)
        body = QHBoxLayout()

        left = QGroupBox('매크로 그룹'); ll = QVBoxLayout(left); self.group_list = QListWidget(); self.group_list.installEventFilter(self); self.group_list.itemDoubleClicked.connect(lambda _: self.rename_group()); ll.addWidget(self.group_list, 1)
        for text, slot in [('그룹 새로 만들기', self.add_group), ('그룹 불러오기', self.import_group), ('그룹 저장', self.export_group), ('그룹 삭제', self.delete_group)]:
            b = QPushButton(text); b.clicked.connect(slot); ll.addWidget(b)
        body.addWidget(left, 1)

        mid = QGroupBox('그룹 구성'); ml = QVBoxLayout(mid)
        self.group_chain_table = QTableWidget(0, 3); self.group_chain_table.setHorizontalHeaderLabels(['No', '체인 이름', '대기시간(초)']); self.group_chain_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.group_chain_table.setEditTriggers(QAbstractItemView.NoEditTriggers); self.group_chain_table.setAlternatingRowColors(True)
        h = self.group_chain_table.horizontalHeader(); h.setSectionResizeMode(0, QHeaderView.ResizeToContents); h.setSectionResizeMode(1, QHeaderView.Stretch); h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.group_chain_table.cellDoubleClicked.connect(lambda *_: self.edit_group_chain()); ml.addWidget(self.group_chain_table, 1)
        row = QHBoxLayout()
        for text, slot in [('체인 불러오기', self.add_chain_to_group), ('선택 체인 제거', self.remove_chain_from_group), ('선택 체인 편집', self.edit_group_chain), ('선택 체인 위로 ▲', self.move_group_chain_up), ('선택 체인을 아래로 ▼', self.move_group_chain_down)]:
            b = QPushButton(text); b.clicked.connect(slot); row.addWidget(b)
        ml.addLayout(row); body.addWidget(mid, 3)

        right = QGroupBox('그룹 재생 설정'); form = QFormLayout(right)
        self.g_inf = QRadioButton('무한반복'); self.g_count = QRadioButton('횟수'); self.g_time = QRadioButton('시간(분)'); self.g_inf.setChecked(True)
        radios = QHBoxLayout(); [radios.addWidget(x) for x in (self.g_inf, self.g_count, self.g_time)]; rw = QWidget(); rw.setLayout(radios); form.addRow('반복 방식', rw)
        self.g_repeat = QSpinBox(); self.g_repeat.setRange(1, 999999); self.g_repeat.setValue(1); form.addRow('횟수', self.g_repeat)
        self.g_minutes = QDoubleSpinBox(); self.g_minutes.setRange(.1, 999999); self.g_minutes.setDecimals(2); self.g_minutes.setValue(10); self.g_minutes.setSuffix(' 분'); form.addRow('시간', self.g_minutes)
        self.g_cycle_wait = QDoubleSpinBox(); self.g_cycle_wait.setRange(0, 3600); self.g_cycle_wait.setDecimals(2); form.addRow('전체 반복 대기(초)', self.g_cycle_wait)
        self.g_speed = QComboBox(); self.g_speed.addItems(['1.0x','1.2x','1.5x','2.0x','3.0x','5.0x']); form.addRow('재생 속도', self.g_speed)
        self.g_default_acc = QDoubleSpinBox(); self.g_default_acc.setRange(.01, 1); self.g_default_acc.setDecimals(2); self.g_default_acc.setValue(.80); form.addRow('기본 이미지 정확도', self.g_default_acc)
        self.g_background = QCheckBox('비활성(백그라운드) 입력 모드'); form.addRow('입력 방식', self.g_background)
        self.g_target_title = QLineEdit(); self.g_target_title.setPlaceholderText('창 이름(제목)'); form.addRow('창 이름', self.g_target_title)
        self.g_target_process = QLineEdit(); self.g_target_process.setPlaceholderText('프로세스 이름 예: Game.exe'); form.addRow('프로세스 이름', self.g_target_process)
        tr = QHBoxLayout(); self.g_select_target = QPushButton('창 선택'); self.g_current_target = QPushButton('현재 창 가져오기'); tr.addWidget(self.g_select_target); tr.addWidget(self.g_current_target); tw = QWidget(); tw.setLayout(tr); form.addRow('', tw)
        self.g_target_status = QLabel('대상 창: 아직 선택되지 않음'); form.addRow('선택 상태', self.g_target_status)
        note = QLabel('※ 비활성 모드는 실제 마우스를 움직이지 않고 Windows 백그라운드 메시지를 대상 창으로 보냅니다. 대상 프로그램이 이를 지원하지 않을 수 있습니다.'); note.setWordWrap(True); form.addRow('', note)
        body.addWidget(right, 2); root.addLayout(body, 1)

        self.group_list.currentRowChanged.connect(self.refresh_group_chains)
        for w in (self.g_inf, self.g_count, self.g_time): w.toggled.connect(self._update_group_repeat_controls); w.toggled.connect(self._group_settings_changed)
        for w in (self.g_repeat, self.g_minutes, self.g_cycle_wait, self.g_speed, self.g_default_acc, self.g_background):
            sig = getattr(w, 'valueChanged', None) or getattr(w, 'currentTextChanged', None) or getattr(w, 'toggled', None)
            if sig: sig.connect(self._group_settings_changed)
        self.g_target_title.textChanged.connect(self._group_settings_changed); self.g_target_process.textChanged.connect(self._group_settings_changed)
        self.g_select_target.clicked.connect(self.select_group_target); self.g_current_target.clicked.connect(self.select_group_target)
        self._update_group_repeat_controls(); return page

    def setup_hotkeys(self):
        self.hotkey_action.connect(self._handle_hotkey_action)
        pressed = set()
        def on_press(key):
            try:
                pressed.add(key)
                if keyboard.Key.shift in pressed:
                    if key == keyboard.Key.f3: self.hotkey_action.emit('group_start')
                    elif key == keyboard.Key.f4: self.hotkey_action.emit('group_stop')
                    elif key == keyboard.Key.f5: self.hotkey_action.emit('group_pause')
                    else: return
                    return
                action = {keyboard.Key.f1:'start_record', keyboard.Key.f2:'stop_record', keyboard.Key.f3:'start_play', keyboard.Key.f4:'stop_play', keyboard.Key.f5:'toggle_pause'}.get(key)
                if action: self.hotkey_action.emit(action)
            except Exception:
                pass
        def on_release(key):
            try: pressed.discard(key)
            except Exception: pass
        self.hotkey_listener = core.keyboard.Listener(on_press=on_press, on_release=on_release); self.hotkey_listener.daemon=True; self.hotkey_listener.start()

    def handle_hotkey(self, action):
        if action == 'group_start': return self.start_group_play()
        if action == 'group_stop': return self.stop_group_play()
        if action == 'group_pause': return self.toggle_group_pause()
        return original_handle(self, action)

    original_handle = core.MainWindow._handle_hotkey_action
    original_update = core.MainWindow.update_button_states
    original_close = core.MainWindow.closeEvent
    original_init = core.MainWindow.__init__

    def init(self, *args, **kwargs):
        self.group_playing = False; self.group_paused = False; self._group_worker = None; self._group_signals = None; self._loading_group_settings = False; self._group_target_hwnd = None
        original_init(self, *args, **kwargs)

    def update(self):
        original_update(self); self.update_group_button_states()

    def close(self, event):
        try: self.stop_group_play()
        except Exception: pass
        original_close(self, event)

    core.MainWindow.load_groups = load_groups
    core.MainWindow.save_groups = save_groups
    core.MainWindow.add_group = add_group
    core.MainWindow.rename_group = rename_group
    core.MainWindow.delete_group = delete_group
    core.MainWindow.refresh_groups = refresh_groups
    core.MainWindow.refresh_group_chains = refresh_group_chains
    core.MainWindow.add_chain_to_group = add_chain_to_group
    core.MainWindow.remove_chain_from_group = remove_chain_from_group
    core.MainWindow.edit_group_chain = edit_group_chain
    core.MainWindow.move_group_chain_up = move_group_chain_up
    core.MainWindow.move_group_chain_down = move_group_chain_down
    core.MainWindow.export_group = export_group
    core.MainWindow.import_group = import_group
    core.MainWindow._group_settings_changed = _group_settings_changed
    core.MainWindow._load_group_settings = _load_group_settings
    core.MainWindow._update_group_repeat_controls = _update_group_repeat_controls
    core.MainWindow.select_group_target = select_group_target
    core.MainWindow.current_group_target = current_group_target
    core.MainWindow.start_group_play = start_group_play
    core.MainWindow.stop_group_play = stop_group_play
    core.MainWindow.toggle_group_pause = toggle_group_pause
    core.MainWindow._group_finished = _group_finished
    core.MainWindow._highlight_group_chain = _highlight_group_chain
    core.MainWindow.update_group_button_states = update_group_button_states
    core.MainWindow.group_tab = group_tab
    core.MainWindow.setup_hotkeys = setup_hotkeys
    core.MainWindow._handle_hotkey_action = handle_hotkey
    core.MainWindow.__init__ = init
    core.MainWindow.update_button_states = update
    core.MainWindow.closeEvent = close
    core.MainWindow.eventFilter = group_event_filter

    return core.MainWindow


class GroupWorker(threading.Thread):
    def __init__(self, window, chains, settings, start_index, signals):
        super().__init__(daemon=True)
        self.window = window; self.chains = [norm_chain_static(x) for x in chains]; self.settings = dict(settings); self.start_index = max(0, start_index); self.sig = signals
        self.stop_evt = threading.Event(); self.pause_evt = threading.Event(); self.pause_evt.set(); self.current = None
    def stop(self):
        self.stop_evt.set(); self.pause_evt.set()
        if self.current:
            try: self.current.stop()
            except Exception: pass
    def pause(self):
        self.pause_evt.clear()
        if self.current:
            try: self.current.pause()
            except Exception: pass
    def resume(self):
        self.pause_evt.set()
        if self.current:
            try: self.current.resume()
            except Exception: pass
    def run(self):
        mode=self.settings.get('mode','infinite'); repeat=max(1,int(self.settings.get('repeat',1))); until=time.monotonic()+float(self.settings.get('minutes',10))*60 if mode=='time' else None; count=0
        self.sig.run.emit(f'[{core.now()}] 매크로 그룹 재생 시작 [BUILD 2026-09-26-GROUP-01]')
        try:
            while not self.stop_evt.is_set():
                if mode=='count' and count>=repeat: break
                if mode=='time' and until and time.monotonic()>=until: break
                first=self.start_index if count==0 else 0
                for idx in range(first,len(self.chains)):
                    if self.stop_evt.is_set(): break
                    while not self.pause_evt.is_set() and not self.stop_evt.is_set(): time.sleep(.05)
                    if self.stop_evt.is_set(): break
                    self.sig.status.emit(idx)
                    path=self.chains[idx]['path']; name=Path(path).name
                    self.sig.run.emit(f'[{core.now()}] 그룹 체인 {idx+1}/{len(self.chains)} 시작: {name}')
                    try:
                        data=json.loads(Path(path).read_text(encoding='utf-8'))
                        raw=data.get('steps',[]) if isinstance(data,dict) else []
                        fields={f.name for f in core.dataclass_fields(Step)}
                        steps=[]
                        for item in raw:
                            if isinstance(item,dict):
                                safe={k:v for k,v in item.items() if k in fields}
                                if not isinstance(safe.get('region',[0,0,0,0]),list): safe['region']=[0,0,0,0]
                                if not isinstance(safe.get('events',[]),list): safe['events']=[]
                                steps.append(Step(**safe))
                        chain_settings=dict(self.settings); chain_settings.update({'mode':'count','repeat':1})
                        sig=Signals(); sig.run.connect(self.sig.run.emit)
                        self.current=MacroWorker(steps,chain_settings,sig)
                        self.current.start();
                        while self.current.is_alive() and not self.stop_evt.is_set():
                            if self.pause_evt.is_set():
                                if getattr(self.current,'_paused',False): self.current.resume()
                            else:
                                if not getattr(self.current,'_paused',False): self.current.pause()
                            time.sleep(.03)
                        if self.stop_evt.is_set(): self.current.stop()
                        self.current.join(timeout=2.0)
                        self.current=None
                    except Exception as e:
                        self.sig.run.emit(f'[{core.now()}] 그룹 체인 실행 오류: {name} | {type(e).__name__}: {e}')
                    wait=float(self.chains[idx].get('wait',0.0) or 0.0)
                    end=time.monotonic()+max(0,wait/max(.1,float(self.settings.get('speed',1.0))))
                    while time.monotonic()<end and not self.stop_evt.is_set():
                        while not self.pause_evt.is_set() and not self.stop_evt.is_set(): time.sleep(.05)
                        time.sleep(.02)
                if self.stop_evt.is_set(): break
                count+=1; self.sig.run.emit(f'[{core.now()}] 그룹 반복 {count}회 완료')
                end=time.monotonic()+max(0,float(self.settings.get('cycle_wait',0.0)))/max(.1,float(self.settings.get('speed',1.0)))
                while time.monotonic()<end and not self.stop_evt.is_set(): time.sleep(.02)
        finally:
            self.current=None
            try: self.sig.finished.emit()
            except Exception: pass


def norm_chain_static(value):
    if isinstance(value,str): return {'path':value,'wait':0.0}
    return {'path':str(value.get('path','')),'wait':float(value.get('wait',0.0) or 0.0)} if isinstance(value,dict) else {'path':'','wait':0.0}
