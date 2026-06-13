"""系统托盘管理 — 图标、菜单、通知气泡"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu

from kira_env_manager.utils.logger import logger


class TrayManager(QSystemTrayIcon):
    """系统托盘管理器

    管理托盘图标、右键菜单、通知气泡。
    通过 launch_page 控制实例的启动/停止。
    """

    def __init__(self, main_window, launch_page, parent=None):
        super().__init__(parent)
        self._main_window = main_window
        self._launch_page = launch_page
        self._im = launch_page.instance_manager()

        # 设置图标
        from pathlib import Path
        png_icon = Path(__file__).parent.parent / "app.png"
        if png_icon.exists():
            self.setIcon(QIcon(str(png_icon)))
        else:
            self.setIcon(QIcon(":/qfluentwidgets/images/logo.png"))

        self.setToolTip("Kira Environment Manager")

        # 构建菜单
        self._menu = QMenu()
        self.setContextMenu(self._menu)
        self._build_menu()

        # 连接信号
        self.activated.connect(self._on_activated)
        self._im.instances_changed.connect(self._rebuild_menu)

        self.show()

    def _build_menu(self):
        """构建/重建右键菜单"""
        self._menu.clear()

        show_action = self._menu.addAction("显示窗口")
        show_action.triggered.connect(self._show_window)

        self._menu.addSeparator()

        start_all = self._menu.addAction("启动全部实例")
        start_all.triggered.connect(self._start_all)
        stop_all = self._menu.addAction("停止全部实例")
        stop_all.triggered.connect(self._stop_all)

        self._menu.addSeparator()

        # 实例子菜单
        instances = self._im.instances()
        if instances:
            inst_menu = self._menu.addMenu("实例列表")
            for inst in instances:
                running = inst.is_running()
                icon = "●" if running else "○"
                label = f"{icon} {inst.name} (: {inst.port})"
                action = inst_menu.addAction(label)
                if running:
                    action.triggered.connect(
                        lambda checked, i=inst: self._stop_instance(i)
                    )
                else:
                    action.triggered.connect(
                        lambda checked, i=inst: self._start_instance(i)
                    )

        self._menu.addSeparator()

        # 恢复退出询问
        reset_action = self._menu.addAction("恢复退出询问")
        reset_action.triggered.connect(self._reset_close_action)

        quit_action = self._menu.addAction("退出")
        quit_action.triggered.connect(self._quit_app)

    def _rebuild_menu(self):
        """实例列表变化时重建菜单"""
        self._build_menu()

    def _on_activated(self, reason):
        """托盘图标被激活"""
        if reason == QSystemTrayIcon.DoubleClick:
            self._show_window()

    def _show_window(self):
        """显示主窗口"""
        self._main_window.show()
        self._main_window.raise_()
        self._main_window.activateWindow()

    def _start_all(self):
        self._launch_page._start_all()

    def _stop_all(self):
        self._launch_page._stop_all()

    def _start_instance(self, inst):
        self._launch_page._on_start(inst)

    def _stop_instance(self, inst):
        self._launch_page._on_stop(inst)

    def _reset_close_action(self):
        """恢复退出询问"""
        from kira_env_manager.common.config import set_config as cfg_set
        cfg_set("tray_close_action", "ask")
        self.showMessage(
            "Kira Environment Manager",
            "已恢复关闭时的退出询问",
            QSystemTrayIcon.Information,
            2000,
        )

    def _quit_app(self):
        """完全退出"""
        self._main_window.close()
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().quit()

    def show_minimize_notification(self):
        """显示最小化到托盘的通知"""
        self.showMessage(
            "Kira Environment Manager",
            "程序已最小化到系统托盘\n双击图标恢复窗口",
            QSystemTrayIcon.Information,
            3000,
        )
