# -*- coding: utf-8 -*-
"""Persistent UI tweaks for ShadeLawcro."""
from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QHeaderView

# Single source of truth for the build shown by the application event log.
# main.py assigns this value to lawcro_core.BUILD_ID at startup.
BUILD_ID = "2026-09-26-GROUP-06"


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
        def save_widths(*_):
            try:
                QSettings('ShadeLawcro', 'ShadeLawcroV1').setValue(
                    'chain_editor/header_widths',
                    ','.join(str(header.sectionSize(i)) for i in range(table.columnCount()))
                )
            except Exception:
                pass
        try:
            header.sectionResized.disconnect()
        except Exception:
            pass
        header.sectionResized.connect(save_widths)

    def _apply_group_ui(self):
        table = getattr(self, 'group_chain_table', None)
        if table is not None and table.columnCount() >= 3:
            table.setColumnHidden(0, True)
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            table.setColumnWidth(0, 0)

    def init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        _restore_chain_header(self)
        _apply_group_ui(self)
        QTimer.singleShot(0, lambda: (_restore_chain_header(self), _apply_group_ui(self)))

    MainWindow.__init__ = init
