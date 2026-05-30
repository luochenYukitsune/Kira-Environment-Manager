"""主窗口 - FluentWindow 侧边导航布局"""

import os

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMessageBox

from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon as FIF

from kira_manager.view.home_page import HomePage
from kira_manager.view.env_page import EnvPage
from kira_manager.view.project_page import ProjectPage
from kira_manager.view.launch_page import LaunchPage
from kira_manager.view.browser_page import BrowserPage
from kira_manager.view.log_page import LogPage
from kira_manager.common.constants import WINDOW_WIDTH, WINDOW_HEIGHT


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

        self.initNavigation()
        self.initWindow()

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

        # 关闭导航栏 Acrylic 毛玻璃 —— paintEvent 每帧 gaussianBlur CPU 计算
        self.navigationInterface.setAcrylicEnabled(False)

    def initWindow(self):
        self.resize(WINDOW_WIDTH, WINDOW_HEIGHT)
        self.setWindowTitle("Kira Environment Manager")
        self.setWindowIcon(QIcon(self._icon_path()))
        self.centerOnScreen()

    def centerOnScreen(self):
        from PyQt5.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
        else:
            # 降级方案：使用 QApplication 的 desktopGeometry
            geo = QApplication.desktop().availableGeometry() if hasattr(QApplication, 'desktop') else None
            if geo is None:
                return  # 无法获取屏幕信息，跳过居中
        self.move(
            (geo.width() - self.width()) // 2,
            (geo.height() - self.height()) // 2,
        )

    @staticmethod
    def _icon_path():
        return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'resources', 'icon.png')

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
            from kira_manager.utils.logger import logger
            logger.warning(f"未找到页面: {routeKey}")
            return
        self.stackedWidget.setCurrentWidget(target)
        self.navigationInterface.setCurrentItem(target.objectName())

    def closeEvent(self, event):
        """关闭窗口时停止所有运行中的实例"""
        from kira_manager.utils.logger import logger

        # 清理启动页卡片中的后台线程，避免 QThread destroyed while running
        if hasattr(self, 'launch_page'):
            cards_widget = getattr(self.launch_page, 'cards_widget', None)
            if cards_widget:
                from kira_manager.view.launch_page import InstanceCard
                for card in cards_widget.findChildren(InstanceCard):
                    card.cleanup()

        # 获取运行中的实例
        im = getattr(self.launch_page, "_im", None)
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

                # 停止所有实例
                for inst in running:
                    try:
                        inst.stop()
                        logger.info(f"退出时停止实例: {inst.name}")
                    except Exception as e:
                        logger.error(f"停止实例失败: {inst.name} - {e}")

        # 停止浏览器页面定时器
        if hasattr(self, 'browser_page'):
            self.browser_page.closeEvent(event)

        event.accept()
