# -*- coding: utf-8 -*-
"""ShadeLawcro V1.0 entry point with the macro-group extension."""
import lawcro_core as core
from PySide6.QtCore import QObject, Signal
import group_extension

class GroupSignals(QObject):
    event = Signal(str)
    run = Signal(str)
    status = Signal(int)
    finished = Signal()
    recorded = Signal(object)
    step = Signal(int)

core.Signals = GroupSignals
group_extension.core = core
group_extension.install(core)


def install_group_shift_hotkeys(window):
    """Reliable Shift+F3/F4/F5 listener for the macro-group controls.

    pynput reports the physical left/right Shift keys as Key.shift_l/Key.shift_r,
    not always as the generic Key.shift.  The original group hotkey handler
    checked only Key.shift, so Shift+F3/F4/F5 could be missed.
    """
    pressed = set()

    def on_press(key):
        try:
            pressed.add(key)
            shift_down = core.keyboard.Key.shift_l in pressed or core.keyboard.Key.shift_r in pressed
            if not shift_down:
                return
            action = {
                core.keyboard.Key.f3: 'group_start',
                core.keyboard.Key.f4: 'group_stop',
                core.keyboard.Key.f5: 'group_pause',
            }.get(key)
            if action:
                window.hotkey_action.emit(action)
        except Exception:
            pass

    def on_release(key):
        try:
            pressed.discard(key)
        except Exception:
            pass

    listener = core.keyboard.Listener(on_press=on_press, on_release=on_release)
    listener.daemon = True
    listener.start()
    window._group_shift_hotkey_listener = listener


if __name__ == '__main__':
    app = core.QApplication(core.sys.argv)
    app.setApplicationName(core.APP_NAME)
    window = core.MainWindow()
    install_group_shift_hotkeys(window)
    window.show()
    core.sys.exit(app.exec())
