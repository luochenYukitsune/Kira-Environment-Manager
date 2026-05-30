"""浏览器页面 - 打开外部浏览器查看 WebUI"""

import webbrowser
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    BodyLabel, SubtitleLabel, StrongBodyLabel,
    PushButton, CardWidget, FluentIcon as FIF, isDarkTheme,
)

from kira_manager.utils.logger import logger
from kira_manager.common.constants import BUTTON_HEIGHT_SMALL
from kira_manager.utils.helpers import check_port_open


class InstanceCard(CardWidget):
    """单个实例的浏览器快捷卡片"""

    def __init__(self, instance, parent=None):
        super().__init__(parent)
        self.instance = instance
        self.url = f"http://localhost:{instance.port}"
        self._is_running = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # 左侧信息
        info_layout = QVBoxLayout()
        info_layout.setSpacing(4)

        name_label = StrongBodyLabel(instance.name, self)
        info_layout.addWidget(name_label)

        self._status_label = BodyLabel("", self)
        self._status_label.setStyleSheet("color: #888;")
        info_layout.addWidget(self._status_label)

        layout.addLayout(info_layout, 1)

        # 右侧按钮
        self.open_btn = PushButton(FIF.LINK, "打开 WebUI", self)
        self.open_btn.setFixedWidth(120)
        self.open_btn.clicked.connect(self._open_browser)
        layout.addWidget(self.open_btn)

        # 初始状态
        self._check_status()
        # 定时检查状态
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._check_status)
        self._timer.start(2000)

    def _check_status(self):
        """检查实例运行状态"""
        running = check_port_open("127.0.0.1", self.instance.port)
        if running != self._is_running:
            self._is_running = running
            if running:
                self._status_label.setText(f"运行中  |  {self.url}")
                self._status_label.setStyleSheet("color: #4caf50;")
                self.open_btn.setEnabled(True)
            else:
                self._status_label.setText("未运行")
                self._status_label.setStyleSheet("color: #f44336;")
                self.open_btn.setEnabled(False)

    def _open_browser(self):
        """在外部浏览器中打开"""
        if self._is_running:
            webbrowser.open(self.url)

    def stop_timer(self):
        """停止定时器"""
        self._timer.stop()


class BrowserPage(QWidget):
    """浏览器页面 - 管理并打开各实例的 WebUI"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("browserPage")
        self._cards = {}  # name -> InstanceCard
        self._last_running_names = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(36, 20, 36, 20)
        layout.setSpacing(16)

        # 标题栏
        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("WebUI 浏览器", self))
        header.addStretch()

        open_all_btn = PushButton(FIF.LINK, "全部打开", self)
        open_all_btn.setFixedHeight(BUTTON_HEIGHT_SMALL)
        open_all_btn.clicked.connect(self._open_all)
        header.addWidget(open_all_btn)

        layout.addLayout(header)

        # 提示
        tip = BodyLabel("点击下方卡片的「打开 WebUI」按钮，在系统浏览器中查看实例界面", self)
        tip.setStyleSheet("color: #888;")
        layout.addWidget(tip)

        # 卡片容器
        self._card_container = QWidget(self)
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setContentsMargins(0, 0, 0, 0)
        self._card_layout.setSpacing(8)
        layout.addWidget(self._card_container, 1)

        # 空状态提示
        self.empty_label = BodyLabel("暂无实例\n请先添加并启动 KiraAI 实例", self)
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setStyleSheet("color: #888;")
        layout.addWidget(self.empty_label)

        # 同步定时器
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self._sync_cards)

    def showEvent(self, event):
        super().showEvent(event)
        self._sync_cards()
        self._sync_timer.start(3000)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._sync_timer.stop()

    def _sync_cards(self):
        """同步卡片与实例列表"""
        w = self.window()
        if not w or not hasattr(w, "launch_page"):
            return

        im = getattr(w.launch_page, "_im", None)
        if not im:
            return

        current_names = {inst.name for inst in im.instances()}
        if current_names == self._last_running_names:
            return

        self._last_running_names = current_names.copy()

        # 移除不存在的卡片
        removed = [n for n in self._cards if n not in current_names]
        for n in removed:
            card = self._cards.pop(n)
            card.stop_timer()
            self._card_layout.removeWidget(card)
            card.deleteLater()

        # 添加新卡片
        for inst in im.instances():
            if inst.name not in self._cards:
                card = InstanceCard(inst, self)
                self._cards[inst.name] = card
                self._card_layout.addWidget(card)

        # 更新空状态
        self.empty_label.setVisible(len(self._cards) == 0)

    def open_for_instance(self, instance):
        """为指定实例打开 WebUI"""
        # 确保卡片存在
        self._sync_cards()

        name = instance.name
        card = self._cards.get(name)

        # 检查端口是否开放
        port = instance.cfg.get("port", 5267)
        if check_port_open("127.0.0.1", port):
            webbrowser.open(f"http://localhost:{port}")
        else:
            from kira_manager.utils.logger import notify_warning
            notify_warning("提示", f"实例 {name} 未运行，请先启动", parent=self)

    def _open_all(self):
        """打开所有运行中的实例 WebUI"""
        for card in self._cards.values():
            if card._is_running:
                webbrowser.open(card.url)

    def closeEvent(self, event):
        """关闭时清理"""
        self._sync_timer.stop()
        for card in self._cards.values():
            card.stop_timer()
        super().closeEvent(event)
