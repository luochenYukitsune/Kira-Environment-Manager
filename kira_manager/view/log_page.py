"""日志页面 - 查看和管理 Kira Environment Manager 日志"""

import os
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    TextBrowser, SubtitleLabel, PushButton,
    FluentIcon as FIF,
)

from kira_manager.utils.logger import (
    LOG_DIR, get_log_path, get_startup_offset,
    notify_success, notify_error, notify_warning,
)
from kira_manager.common.constants import PAGE_MARGINS, BUTTON_HEIGHT_SMALL

MAX_DISPLAY_LINES = 500  # 最大显示行数


class LogPage(QWidget):
    """日志查看页面"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("logPage")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(16)

        # 标题栏
        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("日志查看", self))
        header.addStretch()

        self.auto_scroll_btn = PushButton(FIF.SCROLL, "自动滚动", self)
        self.auto_scroll_btn.setCheckable(True)
        self.auto_scroll_btn.setChecked(True)
        self.auto_scroll_btn.setFixedHeight(BUTTON_HEIGHT_SMALL)
        header.addWidget(self.auto_scroll_btn)

        refresh_btn = PushButton(FIF.SYNC, "刷新", self)
        refresh_btn.setFixedHeight(BUTTON_HEIGHT_SMALL)
        refresh_btn.clicked.connect(self._refresh_log)
        header.addWidget(refresh_btn)

        clear_btn = PushButton(FIF.DELETE, "清空日志", self)
        clear_btn.setFixedHeight(BUTTON_HEIGHT_SMALL)
        clear_btn.clicked.connect(self._clear_log)
        header.addWidget(clear_btn)

        open_btn = PushButton(FIF.FOLDER, "打开目录", self)
        open_btn.setFixedHeight(BUTTON_HEIGHT_SMALL)
        open_btn.clicked.connect(self._open_log_dir)
        header.addWidget(open_btn)

        layout.addLayout(header)

        # 日志路径
        self.path_label = SubtitleLabel("", self)
        self.path_label.setStyleSheet("color: #888; font-size: 12px;")
        layout.addWidget(self.path_label)

        # 日志内容
        self.log_browser = TextBrowser(self)
        self.log_browser.setPlaceholderText("日志内容将显示在这里...")
        layout.addWidget(self.log_browser, 1)

        # 自动刷新定时器
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._last_size = 0

        # 初始化
        self._update_path()
        self._refresh_log()

    def showEvent(self, event):
        """页面显示时开始自动刷新"""
        super().showEvent(event)
        self._refresh_timer.start(2000)  # 每2秒刷新
        self._refresh_log()

    def hideEvent(self, event):
        """页面隐藏时停止刷新"""
        super().hideEvent(event)
        self._refresh_timer.stop()

    def _update_path(self):
        """更新日志路径显示"""
        log_path = get_log_path()
        self.path_label.setText(f"日志文件: {log_path}")

    def _auto_refresh(self):
        """自动刷新（仅在文件变化时）"""
        log_path = get_log_path()
        if not os.path.exists(log_path):
            return

        try:
            current_size = os.path.getsize(log_path)
            if current_size != self._last_size:
                self._refresh_log()
        except OSError:
            pass

    def _read_log_since_startup(self):
        """只读取本次启动后的日志内容"""
        log_path = get_log_path()
        if not os.path.exists(log_path):
            return ""

        try:
            startup_offset = get_startup_offset()

            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                # 如果有启动偏移量，跳过之前的日志
                if startup_offset > 0:
                    try:
                        f.seek(startup_offset)
                    except OSError:
                        f.seek(0)

                lines = f.readlines()

                # 限制显示行数
                if len(lines) > MAX_DISPLAY_LINES:
                    lines = lines[-MAX_DISPLAY_LINES:]

                return "".join(lines)
        except Exception as e:
            return f"读取日志失败: {e}"

    def _refresh_log(self):
        """刷新日志内容"""
        log_path = get_log_path()
        if not os.path.exists(log_path):
            self.log_browser.setPlainText("日志文件不存在")
            return

        content = self._read_log_since_startup()

        if not content:
            content = "(本次启动后暂无日志)"

        self.log_browser.setPlainText(content)

        try:
            self._last_size = os.path.getsize(log_path)
        except OSError:
            pass

        # 自动滚动到底部
        if self.auto_scroll_btn.isChecked():
            cursor = self.log_browser.textCursor()
            cursor.movePosition(cursor.MoveOperation.End)
            self.log_browser.setTextCursor(cursor)

    def _clear_log(self):
        """清空日志文件"""
        log_path = get_log_path()
        if not os.path.exists(log_path):
            return

        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("")
            self.log_browser.clear()
            self._last_size = 0
            notify_success("已清空", "日志文件已清空", parent=self)
        except Exception as e:
            notify_error("失败", f"清空日志失败: {e}", parent=self)

    def _open_log_dir(self):
        """打开日志目录"""
        import subprocess
        if os.path.exists(LOG_DIR):
            subprocess.Popen(["explorer", str(LOG_DIR)])
        else:
            notify_warning("提示", "日志目录不存在", parent=self)
