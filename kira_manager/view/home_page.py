"""首页 - 状态概览仪表盘"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFrame

from qfluentwidgets import (
    CardWidget, IconWidget, PrimaryPushButton,
    BodyLabel, SubtitleLabel, TitleLabel, StrongBodyLabel,
    FluentIcon as FIF, setFont,
)

from kira_manager.utils.python_env import detect_python
from kira_manager.utils.project import (
    check_kira_version, is_kira_project, check_git_installed,
)
from kira_manager.utils.helpers import status_color, get_project_path_fallback
from kira_manager.common.constants import PAGE_MARGINS


class StatusCard(CardWidget):
    """状态指示卡片 - 带图标和颜色指示"""

    def __init__(self, icon, title, parent=None):
        super().__init__(parent)
        self.setMinimumSize(190, 108)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 14, 20, 14)
        layout.setSpacing(6)

        header = QHBoxLayout()
        self.icon_widget = IconWidget(icon, self)
        self.icon_widget.setFixedSize(22, 22)
        header.addWidget(self.icon_widget)

        self.title_label = BodyLabel(title, self)
        header.addWidget(self.title_label)
        header.addStretch()
        layout.addLayout(header)

        self.value_label = StrongBodyLabel("---", self)
        setFont(self.value_label, 15)
        self.value_label.setWordWrap(True)
        layout.addWidget(self.value_label)

        layout.addStretch()

    def set_value(self, text, color=None):
        self.value_label.setText(text)
        if color:
            self.value_label.setStyleSheet(f"color: {color};")


class HomePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("homePage")

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(*PAGE_MARGINS)
        self.main_layout.setSpacing(20)

        # 标题区
        title = TitleLabel("Kira Environment Manager", self)
        self.main_layout.addWidget(title)

        subtitle = BodyLabel("管理你的 KiraAI 数字生命", self)
        self.main_layout.addWidget(subtitle)

        # 状态卡片
        self.cards_layout = QHBoxLayout()
        self.cards_layout.setSpacing(16)

        self.python_card = StatusCard(FIF.CODE, "Python", self)
        self.kira_card = StatusCard(FIF.ROBOT, "KiraAI", self)
        self.git_card = StatusCard(FIF.GITHUB, "Git", self)
        self.run_card = StatusCard(FIF.PLAY, "运行状态", self)

        self.cards_layout.addWidget(self.python_card, 1)
        self.cards_layout.addWidget(self.kira_card, 1)
        self.cards_layout.addWidget(self.git_card, 1)
        self.cards_layout.addWidget(self.run_card, 1)

        self.main_layout.addLayout(self.cards_layout)

        # 分隔线
        sep = QFrame(self)
        sep.setFrameShape(QFrame.HLine)
        self.main_layout.addWidget(sep)

        # 快捷操作
        self.main_layout.addWidget(SubtitleLabel("快捷操作", self))

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)

        env_btn = PrimaryPushButton(FIF.DEVELOPER_TOOLS, "环境配置", self)
        env_btn.clicked.connect(lambda: self._navigate("envPage"))
        btn_layout.addWidget(env_btn)

        proj_btn = PrimaryPushButton(FIF.DOWNLOAD, "项目管理", self)
        proj_btn.clicked.connect(lambda: self._navigate("projectPage"))
        btn_layout.addWidget(proj_btn)

        launch_btn = PrimaryPushButton(FIF.PLAY, "启动管理", self)
        launch_btn.clicked.connect(lambda: self._navigate("launchPage"))
        btn_layout.addWidget(launch_btn)

        btn_layout.addStretch()
        self.main_layout.addLayout(btn_layout)

        self.main_layout.addStretch(1)

        self.refresh_status()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh_status()

    def _navigate(self, route_key):
        w = self.window()
        if w and hasattr(w, "switchToQWidget"):
            w.switchToQWidget(route_key)

    def update_running_status(self, count):
        """由启动页调用，更新运行状态 —— count: 运行中的实例数"""
        if count > 0:
            self.run_card.set_value(f"运行中 ({count}个)", status_color(True))
        else:
            self.run_card.set_value("未运行", status_color(None))

    def refresh_status(self, force=False):

        # Python（仅首次检测，运行时不会变）
        v, _ = detect_python()
        if v:
            self.python_card.set_value(f"Python {v}", status_color(True))
        else:
            self.python_card.set_value("未检测到", status_color(False))

        # KiraAI
        path = get_project_path_fallback()
        if path and is_kira_project(path):
            ver = check_kira_version(path) or "未知"
            self.kira_card.set_value(ver, status_color(True))
        else:
            self.kira_card.set_value("未安装", status_color("warn"))

        # Git
        gv = check_git_installed()
        if gv:
            self.git_card.set_value(gv, status_color(True))
        else:
            self.git_card.set_value("未安装", status_color(False))

        # 运行状态 - 从启动页读取
        w = self.window()
        if w and hasattr(w, "launch_page") and hasattr(w.launch_page, "_im"):
            self.update_running_status(w.launch_page._im.running_count())
        else:
            self.run_card.set_value("未运行", status_color(None))
