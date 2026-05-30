"""项目管理页 - KiraAI 下载、更新、版本管理"""

import os
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFileDialog, QScrollArea,
)

from qfluentwidgets import (
    SettingCardGroup, PushSettingCard, PrimaryPushSettingCard,
    StateToolTip, HyperlinkButton,
    TextBrowser, SubtitleLabel, FluentIcon as FIF,
)

from kira_manager.utils.project import (
    check_kira_version, is_kira_project, clone_repo,
    update_project, check_git_installed, KIRA_GITHUB_URL,
)
from kira_manager.utils.helpers import append_and_scroll, get_project_path_fallback
from kira_manager.utils.logger import (
    logger, notify_info, notify_success, notify_warning, notify_error,
)
from kira_manager.common.config import get as cfg_get, set_config as cfg_set, DEFAULT_CONFIG
from kira_manager.common.constants import PAGE_MARGINS


class GitWorker(QThread):
    """后台 git 操作"""
    line_output = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, action, *args):
        super().__init__()
        self.action = action
        self.args = args

    def run(self):
        cb = lambda line: self.line_output.emit(line)
        if self.action == "clone":
            ok, msg = clone_repo(*self.args, output_callback=cb)
        elif self.action == "pull":
            ok, msg = update_project(*self.args, output_callback=cb)
        else:
            ok, msg = False, "未知操作"
        self.finished.emit(ok, msg)


class ProjectPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("projectPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._worker = None
        self._state_tooltip = None

        container = QWidget(self)
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(16)

        layout.addWidget(SubtitleLabel("项目管理", container))

        # === 项目路径 ===
        self.path_group = SettingCardGroup("项目路径", container)

        self._auto_detect_path()
        current_path = cfg_get("project_path")
        self.path_card = PushSettingCard(
            "浏览", FIF.FOLDER, "KiraAI 项目目录",
            current_path or "未设置", self.path_group,
        )
        self.path_card.clicked.connect(self._select_project)
        self.path_group.addSettingCard(self.path_card)

        layout.addWidget(self.path_group)

        # === 仓库 ===
        self.repo_group = SettingCardGroup("GitHub 仓库", container)

        repo_url = cfg_get("kira_repo_url") or KIRA_GITHUB_URL
        self.repo_card = PushSettingCard(
            "重置", FIF.GITHUB, "仓库地址",
            repo_url, self.repo_group,
        )
        self.repo_group.addSettingCard(self.repo_card)
        self.repo_card.clicked.connect(self._reset_repo_url)

        layout.addWidget(self.repo_group)

        # === 操作 ===
        self.action_group = SettingCardGroup("操作", container)

        self.clone_card = PrimaryPushSettingCard(
            "下载", FIF.DOWNLOAD, "下载 KiraAI",
            "从 GitHub 克隆最新代码", self.action_group,
        )
        self.clone_card.clicked.connect(self._clone_project)
        self.action_group.addSettingCard(self.clone_card)

        self.update_card = PushSettingCard(
            "更新", FIF.UPDATE, "更新项目",
            "git pull 拉取最新代码", self.action_group,
        )
        self.update_card.clicked.connect(self._update_project)
        self.action_group.addSettingCard(self.update_card)

        layout.addWidget(self.action_group)

        # === 版本信息 ===
        self.info_group = SettingCardGroup("版本信息", container)

        ver = self._get_version_string()
        self.version_card = PushSettingCard(
            "检查", FIF.INFO, "当前版本",
            ver, self.info_group,
        )
        self.version_card.clicked.connect(self._check_version)
        self.info_group.addSettingCard(self.version_card)

        git_ver = check_git_installed()
        self.git_card = PushSettingCard(
            "检测", FIF.GITHUB, "Git",
            git_ver or "未安装 - 点击下载", self.info_group,
        )
        self.git_card.clicked.connect(self._open_git_download)
        self.info_group.addSettingCard(self.git_card)

        layout.addWidget(self.info_group)

        # 日志输出
        self.console = TextBrowser(container)
        self.console.setPlaceholderText("操作日志...")
        self.console.setMaximumHeight(220)
        self.console.setMinimumHeight(120)
        layout.addWidget(self.console)

        layout.addStretch(1)

    def _auto_detect_path(self):
        """自动检测当前运行的 KiraAI 目录"""
        if cfg_get("project_path"):
            return
        path = get_project_path_fallback()
        if path:
            cfg_set("project_path", path)

    def _reset_repo_url(self):
        default = DEFAULT_CONFIG.get("kira_repo_url", "https://github.com/xxynet/KiraAI")
        cfg_set("kira_repo_url", default)
        self.repo_card.setContent(default)

    def _get_version_string(self):
        path = get_project_path_fallback()
        if path:
            return check_kira_version(path) or "未知"
        return "未检测到"

    def _select_project(self):
        path = QFileDialog.getExistingDirectory(self, "选择 KiraAI 项目目录")
        if not path:
            return
        if is_kira_project(path):
            cfg_set("project_path", path)
            self.path_card.setContent(path)
            ver = check_kira_version(path) or "未知"
            self.version_card.setContent(ver)
            notify_success("已设置", f"项目: {path}\n版本: {ver}", parent=self)
        else:
            notify_error("无效", "所选目录不是有效的 KiraAI 项目", parent=self)

    def _clone_project(self):
        if not check_git_installed():
            notify_error("未安装 Git", "请先安装 Git: https://git-scm.com/", parent=self)
            return

        default_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        target = QFileDialog.getExistingDirectory(self, "选择下载目录", default_dir)
        if not target:
            return

        kira_dir = os.path.join(target, "KiraAI")
        url = cfg_get("kira_repo_url") or KIRA_GITHUB_URL

        self.console.clear()
        self.clone_card.setEnabled(False)

        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)

        self._state_tooltip = StateToolTip(
            "正在下载 KiraAI", "请稍候...", self.window(),
        )
        self._state_tooltip.move(self._state_tooltip.getSuitablePos())
        self._state_tooltip.show()

        self._worker = GitWorker("clone", url, kira_dir)
        self._worker.line_output.connect(self._on_log_line)
        self._worker.finished.connect(self._on_clone_done)
        self._worker.start()

    def _update_project(self):
        project_path = cfg_get("project_path")
        if not project_path:
            notify_warning("提示", "请先选择项目路径", parent=self)
            return

        self.console.clear()
        self.update_card.setEnabled(False)

        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)

        self._state_tooltip = StateToolTip(
            "正在更新", "git pull...", self.window(),
        )
        self._state_tooltip.move(self._state_tooltip.getSuitablePos())
        self._state_tooltip.show()

        self._worker = GitWorker("pull", project_path)
        self._worker.line_output.connect(self._on_log_line)
        self._worker.finished.connect(self._on_update_done)
        self._worker.start()

    def _on_log_line(self, line):
        append_and_scroll(self.console, line)

    def _on_clone_done(self, ok, msg):
        self.clone_card.setEnabled(True)
        self._finish_op(ok, msg)

        if ok and self._worker and len(self._worker.args) > 1:
            kira_dir = self._worker.args[1]
            cfg_set("project_path", kira_dir)
            self.path_card.setContent(kira_dir)
            ver = check_kira_version(kira_dir) or "未知"
            self.version_card.setContent(ver)

    def _on_update_done(self, ok, msg):
        self.update_card.setEnabled(True)
        self._finish_op(ok, msg)
        project_path = cfg_get("project_path")
        if project_path:
            ver = check_kira_version(project_path) or "未知"
            self.version_card.setContent(ver)

    def _finish_op(self, ok, msg):
        if self._state_tooltip:
            self._state_tooltip.setContent(msg)
            self._state_tooltip.setState(True)
            self._state_tooltip = None

        if ok:
            notify_success("成功", msg, parent=self)
        else:
            notify_error("失败", msg, parent=self)

    def _check_version(self):
        path = get_project_path_fallback()
        if not path:
            notify_warning("提示", "请先选择项目路径", parent=self)
            return
        ver = check_kira_version(path)
        if ver:
            self.version_card.setContent(ver)
            notify_success("版本", f"KiraAI 版本: {ver}", parent=self)
        else:
            notify_warning("无法检测", "未能从项目中检测到版本号", parent=self)

    def _open_git_download(self):
        import webbrowser
        webbrowser.open("https://git-scm.com/downloads")
