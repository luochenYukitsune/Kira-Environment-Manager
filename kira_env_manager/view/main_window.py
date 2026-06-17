"""主窗口 - FluentWindow 侧边导航布局"""

from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMessageBox

from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon as FIF

from kira_env_manager.view.home_page import HomePage
from kira_env_manager.view.env_page import EnvPage
from kira_env_manager.view.project_page import ProjectPage
from kira_env_manager.view.launch_page import LaunchPage
from kira_env_manager.view.browser_page import BrowserPage
from kira_env_manager.view.log_page import LogPage
from kira_env_manager.common.constants import WINDOW_WIDTH, WINDOW_HEIGHT
from kira_env_manager.utils.tray_manager import TrayManager
from kira_env_manager.common.config import get as cfg_get, set_config as cfg_set


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()

        # 关闭 Mica 毛玻璃背景 —— 每次动画帧都触发 DWM 合成，严重拖低帧率
        self.setMicaEffectEnabled(False)

        self.home_page = HomePage(self)
        self.env_page = EnvPage(self)
        self.project_page = ProjectPage(self)
        self.launch_page = LaunchPage(self)
        self.browser_page = BrowserPage(self)
        self.log_page = LogPage(self)

        # 依赖安装完成后自动刷新启动管理页卡片
        self.env_page.dependencies_changed.connect(
            self.launch_page._refresh_all_cards_deps
        )

        self.initNavigation()
        self.initWindow()

        # 创建系统托盘
        self._tray = TrayManager(self, self.launch_page, self)

    def initNavigation(self):
        self.addSubInterface(
            self.home_page, FIF.HOME, "首页",
            position=NavigationItemPosition.SCROLL,
        )
        self.addSubInterface(
            self.env_page, FIF.DEVELOPER_TOOLS, "环境配置",
            position=NavigationItemPosition.SCROLL,
        )
        self.addSubInterface(
            self.project_page, FIF.DOWNLOAD, "项目管理",
            position=NavigationItemPosition.SCROLL,
        )
        self.addSubInterface(
            self.launch_page, FIF.PLAY, "启动管理",
            position=NavigationItemPosition.SCROLL,
        )
        self.addSubInterface(
            self.browser_page, FIF.LINK, "浏览器",
            position=NavigationItemPosition.SCROLL,
        )
        self.addSubInterface(
            self.log_page, FIF.DOCUMENT, "日志",
            position=NavigationItemPosition.SCROLL,
        )
        # 关闭导航栏 Acrylic 毛玻璃
        self.navigationInterface.setAcrylicEnabled(False)

    def initWindow(self):
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowTitle("Kira Environment Manager")
        png_icon = Path(__file__).parent.parent / "app.png"
        if png_icon.exists():
            self.setWindowIcon(QIcon(str(png_icon)))
        else:
            self.setWindowIcon(QIcon(":/qfluentwidgets/images/logo.png"))
        self.centerOnScreen()

    def centerOnScreen(self):
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
        else:
            geo = QApplication.desktop().availableGeometry() if hasattr(QApplication, 'desktop') else None
            if geo is None:
                return
        self.move(
            (geo.width() - self.width()) // 2,
            (geo.height() - self.height()) // 2,
        )

    def changeEvent(self, event):
        if event.type() == event.WindowStateChange:
            if self.windowState() & Qt.WindowMinimized:
                QTimer.singleShot(100, self._minimize_to_tray)
        super().changeEvent(event)

    def _minimize_to_tray(self):
        self.hide()
        if hasattr(self, '_tray'):
            self._tray.show_minimize_notification()

    def switchToQWidget(self, routeKey):
        targets = {
            "homePage": self.home_page,
            "envPage": self.env_page,
            "projectPage": self.project_page,
            "launchPage": self.launch_page,
            "browserPage": self.browser_page,
            "logPage": self.log_page,
        }
        target = targets.get(routeKey)
        if target is None:
            from kira_env_manager.utils.logger import logger
            logger.warning(f"未找到页面: {routeKey}")
            return
        self.stackedWidget.setCurrentWidget(target)
        self.navigationInterface.setCurrentItem(target.objectName())

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def closeEvent(self, event):
        from PyQt5.QtWidgets import QCheckBox
        from kira_env_manager.utils.logger import logger

        action = cfg_get("tray_close_action")

        if action == "ask":
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("Kira Environment Manager")
            msg_box.setText("要关闭程序还是最小化到系统托盘？")
            msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel)
            msg_box.button(QMessageBox.Yes).setText("最小化到托盘")
            msg_box.button(QMessageBox.No).setText("退出")
            msg_box.setDefaultButton(QMessageBox.Yes)

            cb = QCheckBox("不再询问，记住我的选择")
            msg_box.setCheckBox(cb)

            reply = msg_box.exec_()

            if reply == QMessageBox.Cancel:
                event.ignore()
                return

            if cb.isChecked():
                cfg_set("tray_close_action", "minimize" if reply == QMessageBox.Yes else "exit")

            if reply == QMessageBox.Yes:
                event.ignore()
                QTimer.singleShot(50, self._minimize_to_tray)
                return

        elif action == "minimize":
            event.ignore()
            QTimer.singleShot(50, self._minimize_to_tray)
            return

        if hasattr(self, 'launch_page'):
            cards_widget = getattr(self.launch_page, 'cards_widget', None)
            if cards_widget:
                from kira_env_manager.view.launch_page import InstanceCard
                for card in cards_widget.findChildren(InstanceCard):
                    card.cleanup()

        im = getattr(self.launch_page, "instance_manager", lambda: None)()
        if im:
            running = [inst for inst in im.instances() if inst.is_running()]
            if running:
                names = ", ".join(inst.name for inst in running)
                reply = QMessageBox.question(
                    self, "确认退出",
                    f"以下实例正在运行中:\n{names}\n\n是否停止并退出？",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    event.ignore()
                    return

                for inst in running:
                    try:
                        inst.stop()
                        logger.info(f"退出时停止实例: {inst.name}")
                    except Exception as e:
                        logger.error(f"停止实例失败: {inst.name} - {e}")

        if hasattr(self, 'browser_page'):
            self.browser_page.cleanup()

        event.accept()
