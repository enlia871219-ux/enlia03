# -*- coding: utf-8 -*-
"""ShadeLawcro V1.0 entry point with the macro-group extension."""
import lawcro_core as core
import group_extension

group_extension.core = core
group_extension.install(core)

if __name__ == '__main__':
    app = core.QApplication(core.sys.argv)
    app.setApplicationName(core.APP_NAME)
    window = core.MainWindow()
    window.show()
    core.sys.exit(app.exec())
