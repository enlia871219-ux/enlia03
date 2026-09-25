# -*- coding: utf-8 -*-
"""Persistent UI tweaks for ShadeLawcro."""
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QHeaderView

BUILD_ID = "2026-09-26-GROUP-04"


def install(core):
    MainWindow = core.MainWindow
    original_init = MainWindow.__init__

    def _restore_chain_header(self):
        table = getattr(self, 'table', None)
        if table is None:
            return
        settings = QSettings('ShadeLawcro', 'ShadeLawcroV1')
        raw = settings.value('chain_editor/header_widths', None)
        if raw is not None:
            try:
                if isinstance(raw, str):
                    widths = [int(x) for x in raw.split(',') if x.strip()]
                else:
                    widths = [int(x) for x in raw]
                header = table.horizontalHeader()
                if len(widths) == table.columnCount():
                    header.blockSignals(True)
                    for i, width in enumerate(widths):
                        if width >= header.minimumSectionSize():
                            header.resizeSection(i, width)
                    header.blockSignals(False)
            except Exception:
                pass

        header = table.horizontalHeader()
        if getattr(self, '_chain_header_persistence_installed', False):
            return
        self._chain_header_persistence_installed = True

        def save_widths(section, old_size, new_size):
            try:
                widths = [header.sectionSize(i) for i in range(table.columnCount())]
                settings.setValue('chain_editor/header_widths', ','.join(map(str, widths)))
                settings.sync()
            except Exception:
                pass

        header.sectionResized.connect(save_widths)
        QTimer.singleShot(0, _restore_chain_header)

    def _apply_group_ui(self):
        table = getattr(self, 'group_chain_table', None)
        if table is not None:
            # The No column is intentionally hidden. The row order remains the
            # actual playback order internally, so there is no duplicate number.
            table.setColumnHidden(0, True)
            # Do not use table.horizontalHeader().Fixed here: Fixed is a
            # QHeaderView.ResizeMode enum, not an instance attribute.
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)

        # Match the macro-chain action-button palette.
        for name, object_name in (
            ('g_start_btn', 'blueAction'),
            ('g_pause_btn', 'greenAction'),
            ('g_stop_btn', 'redAction'),
        ):
            button = getattr(self, name, None)
            if button is not None:
                button.setObjectName(object_name)
                self.style().unpolish(button)
                self.style().polish(button)
                button.update()

        _restore_chain_header(self)

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _apply_group_ui(self)

    MainWindow.__init__ = init
    return MainWindow
