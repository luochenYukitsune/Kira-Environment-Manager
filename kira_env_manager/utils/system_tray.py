"""系统托盘管理 — 最小化到托盘、实例快捷启停"""

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction


class SystemTrayManager(QObject):
    """系统托盘图标 + 右键菜单管理

    通过信号向主窗口传达用户操作，不直接持有窗口引用。
    """
    show_window_requested = pyqtSignal()
    exit_requested = pyqtSignal()
    start_instance_requested = pyqtSignal(str)  # instance name
    stop_instance_requested = pyqtSignal(str)   # instance name
    open_webui_requested = pyqtSignal(str)      # instance name

    def __init__(self, icon_path: str, parent=None):
        super().__init__(parent)
        self._icon_path = icon_path
        self._actions = {}  # instance_name -> (start_action, stop_action, open_action)

        # QSystemTrayIcon
        self._tray = QSystemTrayIcon(parent)
        icon = QIcon(icon_path) if icon_path else QIcon()
        self._tray.setIcon(icon)
        self._tray.setToolTip("Kira Environment Manager")

        # 右键菜单（固定部分）
        self._menu = QMenu()
        self._show_action = QAction("显示主窗口", self._menu)
        self._show_action.triggered.connect(self.show_window_requested.emit)
        self._menu.addAction(self._show_action)
        self._menu.addSeparator()
        # 实例菜单项占位（由 rebuild_instance_menu 填充）
        self._instance_separator = self._menu.addSeparator()
        self._menu.addSeparator()
        self._exit_action = QAction("退出", self._menu)
        self._exit_action.triggered.connect(self.exit_requested.emit)
        self._menu.addAction(self._exit_action)

        self._tray.setContextMenu(self._menu)
        # 双击托盘图标显示主窗口
        self._tray.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window_requested.emit()

    def show(self):
        self._tray.show()

    def hide(self):
        self._tray.hide()

    def is_visible(self) -> bool:
        return self._tray.isVisible()

    def rebuild_instance_menu(self, instances_info):
        """重建实例快捷启停菜单项

        Args:
            instances_info: [(name, is_running, port), ...]
        """
        # 清除旧的实例动作
        for name, actions in self._actions.items():
            for act in actions:
                self._menu.removeAction(act)
        self._actions.clear()

        # 在第一个分隔线后插入实例动作
        insert_pos = self._menu.actions().index(self._instance_separator)

        for name, is_running, port in instances_info:
            label = f"{'▶' if is_running else '●'} {name} ({port})"
            group = QMenu(label, self._menu)

            if is_running:
                open_act = group.addAction("打开 WebUI")
                open_act.triggered.connect(
                    lambda checked, n=name: self.open_webui_requested.emit(n)
                )
                stop_act = group.addAction("停止")
                stop_act.triggered.connect(
                    lambda checked, n=name: self.stop_instance_requested.emit(n)
                )
                self._actions[name] = (None, stop_act, open_act)
            else:
                start_act = group.addAction("启动")
                start_act.triggered.connect(
                    lambda checked, n=name: self.start_instance_requested.emit(n)
                )
                self._actions[name] = (start_act, None, None)

            # 插入到实例分隔线之前
            self._menu.insertMenu(self._instance_separator, group)

    def on_instance_state_changed(self, name, is_running, port):
        """通知托盘实例状态变化（触发票据刷新，需外部调用 rebuild_instance_menu 全量重建）"""
        self._tray.setToolTip(
            f"Kira Environment Manager\n{'●' if is_running else '○'} {name} ({port})"
        )

    def show_message(self, title, message, icon=QSystemTrayIcon.Information, duration=3000):
        if self._tray.supportsMessages():
            self._tray.showMessage(title, message, icon, duration)
