"""主窗口 - FluentWindow 侧边导航布局"""

from pathlib import Path

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QMessageBox

from qfluentwidgets import FluentWindow, NavigationItemPosition, FluentIcon as FIF
from qfluentwidgets import toggleTheme, setTheme, isDarkTheme, Theme

from kira_env_manager.view.home_page import HomePage
from kira_env_manager.view.env_page import EnvPage
from kira_env_manager.view.project_page import ProjectPage
from kira_env_manager.view.launch_page import LaunchPage
from kira_env_manager.view.browser_page import BrowserPage
from kira_env_manager.view.log_page import LogPage
from kira_env_manager.common.constants import WINDOW_WIDTH, WINDOW_HEIGHT
from kira_env_manager.utils.tray_manager import TrayManager
from kira_env_manager.utils.media_player import MusicPlayer
from kira_env_manager.common.config import get as cfg_get, set_config as cfg_set


class MainWindow(FluentWindow):
    closed_by_tray = pyqtSignal()

    def __init__(self):
        super().__init__()

        # 托盘「退出」置 True 以绕过 closeEvent 的最小化/询问分支（见 closeEvent）
        self._force_quit = False

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

        # 背景音乐播放器（自动启动播放）
        try:
            self._music_player = MusicPlayer(self)
        except Exception:
            from kira_env_manager.utils.logger import logger
            logger.warning("背景音乐播放器初始化失败，将以无声模式运行")
            self._music_player = None

        # 恢复暗色模式配置
        dark_mode = cfg_get("dark_mode")
        if dark_mode:
            setTheme(Theme.DARK)
        else:
            setTheme(Theme.LIGHT)
        self._update_app_palette(dark_mode)

        from PyQt5.QtWidgets import QApplication
        self.closed_by_tray.connect(
            QApplication.instance().quit,
            Qt.ConnectionType.UniqueConnection,
        )

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

        # --- 底部操作项 ---

        # 暗色模式切换
        self._dark_mode_item = self.navigationInterface.addItem(
            routeKey="darkModeToggle",
            icon=FIF.BRIGHTNESS,
            text="深色模式",
            onClick=self._toggle_dark_mode,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

        # 背景音乐播放/暂停（图标随播放状态变化）
        self._music_nav_item = self.navigationInterface.addItem(
            routeKey="musicToggle",
            icon=FIF.MUSIC,
            text="背景音乐",
            onClick=self._toggle_music,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

        # 选择自定义音乐文件
        self.navigationInterface.addItem(
            routeKey="musicSelect",
            icon=FIF.MUSIC_FOLDER,
            text="选择音乐",
            onClick=self._select_music,
            selectable=False,
            position=NavigationItemPosition.BOTTOM,
        )

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

    @staticmethod
    def _update_app_palette(dark):
        """暗色调色板 + QComboBox 颜色修复"""
        from PyQt5.QtGui import QPalette, QColor
        from PyQt5.QtWidgets import QApplication
        qApp = QApplication.instance()
        if qApp is None:
            return
        p = QPalette()
        if dark:
            p.setColor(QPalette.Window, QColor(45, 45, 45))
            p.setColor(QPalette.WindowText, QColor(255, 255, 255))
            p.setColor(QPalette.Base, QColor(30, 30, 30))
            p.setColor(QPalette.AlternateBase, QColor(45, 45, 45))
            p.setColor(QPalette.ToolTipBase, QColor(30, 30, 30))
            p.setColor(QPalette.ToolTipText, QColor(255, 255, 255))
            p.setColor(QPalette.Text, QColor(255, 255, 255))
            p.setColor(QPalette.Button, QColor(45, 45, 45))
            p.setColor(QPalette.ButtonText, QColor(255, 255, 255))
            p.setColor(QPalette.BrightText, QColor(255, 0, 0))
            p.setColor(QPalette.Link, QColor(42, 130, 218))
            p.setColor(QPalette.Highlight, QColor(42, 130, 218))
            p.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
            # 只修 QComboBox 下拉列表颜色，不碰全局 QSS
            qApp.setStyleSheet("""
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    color: #ffffff;
    selection-background-color: #2a82da;
    selection-color: #ffffff;
}
""")
        else:
            p = QApplication.style().standardPalette()
            qApp.setStyleSheet("")
        qApp.setPalette(p)

    def _toggle_dark_mode(self):
        """切换深色/浅色主题并持久化到配置"""
        target = Theme.DARK if not isDarkTheme() else Theme.LIGHT
        setTheme(target)
        cfg_set("dark_mode", target == Theme.DARK)
        self._update_app_palette(target == Theme.DARK)

    def _toggle_music(self):
        """切换背景音乐播放/暂停并更新导航图标"""
        if not self._music_player:
            return
        playing = self._music_player.toggle_playback()
        self._music_nav_item.setIcon(FIF.MUSIC if playing else FIF.MUTE)

    def _select_music(self):
        """选择自定义背景音乐文件"""
        if not self._music_player:
            return
        from PyQt5.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景音乐", "",
            "音频文件 (*.mp3 *.wav *.flac *.ogg *.wma);;所有文件 (*)",
        )
        if not path:
            return
        cfg_set("music_path", path)
        ok = self._music_player.load_file(path)
        if ok:
            from kira_env_manager.utils.logger import notify_success
            notify_success("音乐已切换", Path(path).name, parent=self)
            self._music_nav_item.setIcon(FIF.MUSIC)
        else:
            from kira_env_manager.utils.logger import notify_error
            notify_error("音乐加载失败", "文件不存在或无法播放", parent=self)

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

        # 托盘「退出」会置 _force_quit（一次性）；为真时绕过 ask/最小化分支，
        # 直接走"确认运行中实例 → 清理 → 退出"，否则托盘退出在 minimize 模式
        # 下会被 minimize 分支 event.ignore() 无限拦截，程序永远退不掉。
        force_quit = getattr(self, "_force_quit", False)
        self._force_quit = False
        action = cfg_get("tray_close_action")

        if not force_quit:
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

        # ---- 真正退出：先确认并停止运行中的实例 ----
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
                # 等待进程真正结束再退出，避免 stop() 的守护终止线程被解释器
                # 中止、遗留孤儿进程（端口被占、下次启动撞端口）。超时需覆盖
                # POSIX 上 terminate(3s)→kill(2s) 的升级时间。
                for inst in running:
                    try:
                        inst._pm.wait_for_stop(6000)
                    except Exception:
                        pass

        # ---- 清理各页面的后台线程与卡片，避免 "QThread destroyed while running" ----
        if hasattr(self, 'launch_page'):
            cards_widget = getattr(self.launch_page, 'cards_widget', None)
            if cards_widget:
                from kira_env_manager.view.launch_page import InstanceCard
                for card in cards_widget.findChildren(InstanceCard):
                    card.cleanup()

        for page_attr in ('home_page', 'env_page', 'project_page'):
            page = getattr(self, page_attr, None)
            if page is not None and hasattr(page, 'cleanup'):
                try:
                    page.cleanup()
                except Exception as e:
                    logger.error(f"清理页面失败 {page_attr}: {e}")

        if hasattr(self, 'browser_page'):
            self.browser_page.cleanup()

        self.closed_by_tray.emit()
        event.accept()
