"""启动管理页 - 下载安装 KiraAI、多实例管理、控制台"""

import os
import shutil
import stat
import socket
from PyQt5.QtCore import Qt, pyqtSignal, QThread, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QMessageBox, QLabel, QFrame, QDialog, QDialogButtonBox,
    QCheckBox, QLineEdit, QSpinBox, QFileDialog, QProgressBar,
    QPushButton, QInputDialog, QComboBox,
)

from qfluentwidgets import (
    PrimaryPushButton, PushButton,
    TextBrowser, SubtitleLabel,
    StrongBodyLabel, BodyLabel, CardWidget, IconWidget,
    FluentIcon as FIF, setFont, FlowLayout,
    TransparentToolButton, StateToolTip,
)

from kira_manager.utils.instance_manager import InstanceManager
from kira_manager.utils.python_env import (
    get_venv_python, is_venv, create_venv, install_requirements,
    check_dependencies_installed,
)
from kira_manager.utils.project import (
    clone_repo, check_kira_version, is_kira_project,
    check_git_installed, KIRA_GITHUB_URL,
)
from kira_manager.utils.network import test_all_routes, GITHUB_ROUTES, convert_to_clone_url
from kira_manager.utils.helpers import (
    append_and_scroll, get_mirror_for_install,
    build_clone_url_from_results, status_color,
    check_port_open,
)
from kira_manager.utils.logger import (
    logger, notify_info, notify_success, notify_warning, notify_error, notify_critical,
)
from kira_manager.common.config import get as cfg_get, set_config as cfg_set, full as cfg_full, save_full
from kira_manager.view.config_page import ConfigDialog
from kira_manager.common.constants import PAGE_MARGINS, BUTTON_HEIGHT_MEDIUM, BUTTON_HEIGHT_SMALL


def _remove_readonly(func, path, exc_info):
    """处理 Windows 上的只读文件（如 .git 目录中的文件）"""
    os.chmod(path, stat.S_IWRITE)
    func(path)


class CloneWorker(QThread):
    """后台下载 KiraAI"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str, str)  # ok, msg, project_path or server_url changed

    def __init__(self, clone_url, target_dir):
        super().__init__()
        self.clone_url = clone_url
        self.target_dir = target_dir

    def run(self):
        ok, msg = clone_repo(
            self.clone_url, self.target_dir,
            output_callback=lambda line: self.progress.emit(line),
        )
        self.finished.emit(ok, msg, self.target_dir)


class RouteSpeedWorker(QThread):
    """后台测速：避免阻塞 UI 线程"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(object)  # results list

    def __init__(self, repo):
        super().__init__()
        self.repo = repo

    def run(self):
        results = test_all_routes(
            callback=lambda name, lat: self.progress.emit(
                f"  {name}: {lat}ms" if lat else f"  {name}: 超时"
            )
        )
        self.finished.emit(results)


class SetupWorker(QThread):
    """后台: venv 创建 + 依赖安装"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, venv_path, req_path, mirror_url, fallback_mirrors):
        super().__init__()
        self.venv_path = venv_path
        self.req_path = req_path
        self.mirror_url = mirror_url
        self.fallback_mirrors = fallback_mirrors

    def run(self):
        from pathlib import Path

        venv = Path(self.venv_path)

        # 检查 venv 是否有效
        if is_venv(self.venv_path):
            self.progress.emit(f">> 检测到已有虚拟环境: {self.venv_path}\n")
        elif venv.exists():
            # venv 目录存在但无效（可能是损坏的），删除后重建
            self.progress.emit(f">> 检测到无效的虚拟环境目录，正在清理...\n")
            try:
                shutil.rmtree(str(venv))
                self.progress.emit(">> 清理完成\n")
            except Exception as e:
                self.finished.emit(False, f"清理无效 venv 失败: {e}")
                return

            # 重新创建
            self.progress.emit(">> 创建虚拟环境...\n")
            ok, msg = create_venv(self.venv_path)
            if not ok:
                self.finished.emit(False, f"venv 创建失败: {msg}")
                return
            self.progress.emit(f">> {msg}\n")
        else:
            # venv 不存在，直接创建
            self.progress.emit(">> 创建虚拟环境...\n")
            ok, msg = create_venv(self.venv_path)
            if not ok:
                self.finished.emit(False, f"venv 创建失败: {msg}")
                return
            self.progress.emit(f">> {msg}\n")

        # 安装依赖
        self.progress.emit(">> 安装依赖...\n")
        ok, msg = install_requirements(
            self.venv_path, self.req_path,
            mirror_url=self.mirror_url,
            fallback_mirrors=self.fallback_mirrors,
            output_callback=lambda line: self.progress.emit(line),
        )
        self.finished.emit(ok, msg)


class DownloadDialog(QDialog):
    """下载 KiraAI 向导 — 选位置、代理测速、克隆"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("下载并安装 KiraAI")
        self.setMinimumWidth(550)
        self.setMinimumHeight(420)

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 安装位置
        layout.addWidget(BodyLabel("安装位置:", self))
        dir_row = QHBoxLayout()
        self.dir_input = QLineEdit(self)
        default_dir = os.path.join(os.path.expanduser("~"), "Desktop", "KiraAI")
        self.dir_input.setText(default_dir)
        dir_row.addWidget(self.dir_input)
        browse_btn = QPushButton("浏览...", self)
        browse_btn.clicked.connect(self._browse)
        dir_row.addWidget(browse_btn)
        layout.addLayout(dir_row)

        # 仓库地址
        layout.addWidget(BodyLabel("GitHub 仓库:", self))
        self.repo_input = QLineEdit(self)
        self.repo_input.setText(cfg_get("kira_repo_url") or KIRA_GITHUB_URL)
        self.repo_input.setPlaceholderText("xxynet/KiraAI")
        layout.addWidget(self.repo_input)

        # 代理测速
        layout.addWidget(BodyLabel("访问通道:", self))
        self.route_label = BodyLabel("点击测速选择最快通道，或手动选择", self)
        layout.addWidget(self.route_label)

        route_row = QHBoxLayout()
        speed_btn = QPushButton("测速", self)
        speed_btn.clicked.connect(self._speed_test)
        route_row.addWidget(speed_btn)

        self.route_combo = QComboBox(self)
        for name, _, _, desc in GITHUB_ROUTES:
            self.route_combo.addItem(f"{name} - {desc}")
        self.route_combo.setCurrentIndex(0)
        self.route_combo.currentIndexChanged.connect(self._on_route_selected)
        route_row.addWidget(self.route_combo)

        route_row.addStretch()
        self.route_status = BodyLabel("", self)
        route_row.addWidget(self.route_status)
        layout.addLayout(route_row)

        self._best_clone_url = ""
        self._best_route_name = ""

        # CLI 启动参数预埋
        layout.addWidget(BodyLabel("启动参数 (可选):", self))
        self.auth_check = QCheckBox("--disable-webui-auth   (禁用 WebUI 登录认证)", self)
        layout.addWidget(self.auth_check)
        self.noversion_check = QCheckBox("--ignore-webui-version-check   (跳过前端版本检查)", self)
        layout.addWidget(self.noversion_check)
        custom_row = QHBoxLayout()
        custom_row.addWidget(BodyLabel("自定义参数:", self))
        self.custom_args_input = QLineEdit(self)
        self.custom_args_input.setPlaceholderText("例如: --data-dir path")
        custom_row.addWidget(self.custom_args_input)
        layout.addLayout(custom_row)

        # 进度
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.log = TextBrowser(self)
        self.log.setMaximumHeight(120)
        self.log.setPlaceholderText("操作日志...")
        layout.addWidget(self.log)

        layout.addStretch()

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        btns.button(QDialogButtonBox.Ok).setText("开始下载")
        btns.accepted.connect(self._start_download)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._clone_worker = None

    def _browse(self):
        d = QFileDialog.getExistingDirectory(self, "选择安装目录")
        if d:
            self.dir_input.setText(os.path.join(d, "KiraAI"))

    def _on_route_selected(self, index):
        """手动选择通道"""
        if 0 <= index < len(GITHUB_ROUTES):
            route = GITHUB_ROUTES[index]
            repo = self.repo_input.text().strip() or "xxynet/KiraAI"
            self._best_clone_url = convert_to_clone_url(route, repo)
            self._best_route_name = route[0]
            self.route_status.setText(f"已选择: {route[0]}")
            self.route_label.setText(f"手动选择: {route[0]}")

    def _speed_test(self):
        self.route_status.setText("测速中...")
        self.log.clear()
        repo = self.repo_input.text().strip() or "xxynet/KiraAI"

        self._speed_worker = RouteSpeedWorker(repo)
        self._speed_worker.progress.connect(lambda line: self.log.append(line))
        self._speed_worker.finished.connect(self._on_speed_done)
        self._speed_worker.start()

    def _on_speed_done(self, results):
        repo = self.repo_input.text().strip() or "xxynet/KiraAI"
        if results:
            best_name = results[0][0]
            self._best_clone_url, self._best_route_name = build_clone_url_from_results(results, repo)
            self.route_status.setText(f"最快: {best_name}")
            self.route_label.setText(f"已选择: {best_name}")
            # 更新下拉框选中项
            for i, (name, _, _, _) in enumerate(GITHUB_ROUTES):
                if name == best_name:
                    self.route_combo.setCurrentIndex(i)
                    break
        else:
            self.route_status.setText("全部超时")
            self._best_clone_url = self.repo_input.text().strip() or KIRA_GITHUB_URL
            self._best_route_name = "直连"

    def _start_download(self):
        target = self.dir_input.text().strip()
        if not target:
            self.log.append("请选择安装目录\n")
            return
        if os.path.exists(target):
            self.log.append(f"目录已存在: {target}\n")
            return
        if not check_git_installed():
            notify_critical("错误", "未检测到 Git，请先安装:\nhttps://git-scm.com/", parent=self)
            return

        # 未测速则用默认
        if not self._best_clone_url:
            self._best_clone_url = self.repo_input.text().strip() or KIRA_GITHUB_URL
            self._best_route_name = "直连"

        self.log.clear()
        self.log.append(f">>> 通道: {self._best_route_name}\n")
        self.log.append(f">>> 目标: {target}\n\n")

        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 0)  # 不确定进度

        # 禁用按钮
        for btn in self.findChildren(QPushButton):
            btn.setEnabled(False)

        self._clone_worker = CloneWorker(self._best_clone_url, target)
        self._clone_worker.progress.connect(self._on_progress)
        self._clone_worker.finished.connect(self._on_done)
        self._clone_worker.start()

    def _on_progress(self, line):
        append_and_scroll(self.log, line)

    def _on_done(self, ok, msg, path):
        self.progress_bar.setVisible(False)
        if ok:
            self.log.append(f"\n>> 下载完成: {path}\n")
            self._target_path = path
            self.accept()
        else:
            self.log.append(f"\n>> 下载失败: {msg}\n")
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(False)
            for btn in self.findChildren(QPushButton):
                btn.setEnabled(True)

    def reject(self):
        if self._clone_worker and self._clone_worker.isRunning():
            self._clone_worker.terminate()
            self._clone_worker.wait(3000)
        super().reject()

    def get_result(self):
        extra = []
        if self.auth_check.isChecked():
            extra.append("--disable-webui-auth")
        if self.noversion_check.isChecked():
            extra.append("--ignore-webui-version-check")
        custom = self.custom_args_input.text().strip()
        if custom:
            extra.extend(custom.split())
        return (getattr(self, '_target_path', ''),
                self.repo_input.text().strip() or KIRA_GITHUB_URL,
                self._best_route_name,
                extra)


class _DepsCheckWorker(QThread):
    finished = pyqtSignal(bool, list, str)

    def __init__(self, venv_path, project_path, parent=None):
        super().__init__(parent)
        self.venv_path = venv_path
        self.project_path = project_path

    def run(self):
        if not self.venv_path or not self.project_path:
            self.finished.emit(False, ["无venv"], "无虚拟环境")
            return
        if not is_venv(self.venv_path):
            self.finished.emit(False, ["venv无效"], "虚拟环境无效")
            return
        req = os.path.join(self.project_path, "requirements.txt")
        if not os.path.exists(req):
            self.finished.emit(False, ["无requirements.txt"], "无依赖文件")
            return
        ok, missing, msg = check_dependencies_installed(self.venv_path, req)
        self.finished.emit(ok, missing, msg)


class InstanceCard(CardWidget):
    start_clicked = pyqtSignal(object)
    stop_clicked = pyqtSignal(object)
    remove_clicked = pyqtSignal(object)
    selected = pyqtSignal(object)
    view_clicked = pyqtSignal(object)
    config_clicked = pyqtSignal(object)
    rename_clicked = pyqtSignal(object)

    def __init__(self, instance, parent=None):
        super().__init__(parent)
        self.inst = instance
        self.deps_ok = False
        self._is_running = False
        self.setMinimumWidth(320)
        self.setMinimumHeight(250)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        title_row = QHBoxLayout()
        title_row.addWidget(IconWidget(FIF.ROBOT, self))
        self.name_label = StrongBodyLabel(instance.name, self)
        setFont(self.name_label, 13)
        title_row.addWidget(self.name_label)
        title_row.addStretch()
        self.status_dot = QLabel(self)
        self.status_dot.setFixedSize(10, 10)
        self._update_dot(False)
        title_row.addWidget(self.status_dot)
        layout.addLayout(title_row)

        info_frame = QFrame(self)
        info = QVBoxLayout(info_frame)
        info.setContentsMargins(4, 4, 4, 4)
        info.setSpacing(2)
        self.port_label = BodyLabel(f"端口: {instance.port}", info_frame)
        info.addWidget(self.port_label)
        proj = os.path.basename(instance.project_path) if instance.project_path else "(未设置)"
        info.addWidget(BodyLabel(f"项目: {proj}", info_frame))
        data = instance.data_dir
        info.addWidget(BodyLabel(f"数据: {os.path.basename(data) if data else '(默认)'}", info_frame))
        self.deps_label = BodyLabel("依赖: 检查中...", info_frame)
        info.addWidget(self.deps_label)
        layout.addWidget(info_frame)
        layout.addStretch()

        venv_path = cfg_get("venv_path")
        project_path = instance.project_path or cfg_get("project_path")
        self._deps_worker = _DepsCheckWorker(venv_path, project_path, self)
        self._deps_worker.finished.connect(self._on_deps_checked)
        self._deps_worker.start()

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)

        self.start_btn = PushButton(FIF.PLAY, "启动", self)
        self.start_btn.setFixedHeight(BUTTON_HEIGHT_MEDIUM)
        self.start_btn.clicked.connect(lambda: self.start_clicked.emit(self.inst))
        btn_row.addWidget(self.start_btn)

        self.stop_btn = PushButton(FIF.PAUSE, "停止", self)
        self.stop_btn.setFixedHeight(BUTTON_HEIGHT_MEDIUM)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(lambda: self.stop_clicked.emit(self.inst))
        btn_row.addWidget(self.stop_btn)

        self.view_btn = PushButton(FIF.LINK, "查看", self)
        self.view_btn.setFixedHeight(BUTTON_HEIGHT_MEDIUM)
        self.view_btn.clicked.connect(lambda: self.view_clicked.emit(self.inst))
        btn_row.addWidget(self.view_btn)

        self.config_btn = PushButton(FIF.SETTING, "配置", self)
        self.config_btn.setFixedHeight(BUTTON_HEIGHT_MEDIUM)
        self.config_btn.clicked.connect(lambda: self.config_clicked.emit(self.inst))
        btn_row.addWidget(self.config_btn)

        rename_btn = TransparentToolButton(FIF.EDIT, self)
        rename_btn.setToolTip("重命名")
        rename_btn.clicked.connect(lambda: self.rename_clicked.emit(self.inst))
        btn_row.addWidget(rename_btn)

        btn_row.addStretch()
        remove_btn = TransparentToolButton(FIF.DELETE, self)
        remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.inst))
        btn_row.addWidget(remove_btn)
        layout.addLayout(btn_row)

        # 定时端口检测 - 准确判断是否在运行
        self._port_check_timer = QTimer(self)
        self._port_check_timer.timeout.connect(self._check_port_status)
        self._port_check_timer.start(2000)  # 每2秒检测一次
        QTimer.singleShot(200, self._check_port_status)  # 立即检测一次

    def _on_deps_checked(self, ok, missing, msg):
        self.deps_ok = ok
        if ok:
            self.deps_label.setText("依赖: 已安装")
        else:
            self.deps_label.setText(f"依赖: 缺失 {len(missing)} 个")

    def _check_port_status(self):
        """通过撞端口检测实例是否在运行"""
        port = self.inst.port
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                is_running = True
        except (ConnectionRefusedError, TimeoutError, OSError):
            is_running = False

        # 状态变化时更新UI
        if is_running != self._is_running:
            self._is_running = is_running
            self._update_running_ui(is_running)

    def _update_dot(self, running):
        self.status_dot.setStyleSheet(
            f"background: {status_color(running)}; border-radius: 5px;"
        )

    def _update_running_ui(self, running):
        """更新运行状态UI"""
        self._update_dot(running)
        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)

    def cleanup(self):
        """销毁前调用：断开定时器、停止后台线程，避免资源泄漏"""
        # 断开信号连接防止 timer 在对象析构过程中触发
        self._port_check_timer.timeout.disconnect(self._check_port_status)
        self._port_check_timer.stop()
        # 等待后台线程结束
        if self._deps_worker and self._deps_worker.isRunning():
            self._deps_worker.quit()
            self._deps_worker.wait(3000)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        self.selected.emit(self.inst)


class LaunchPage(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("launchPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._im = InstanceManager(self)
        self._setup_worker = None
        self._state_tip = None

        container = QWidget(self)
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(16)

        # 标题
        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("启动管理", container))
        header.addStretch()

        add_btn = PrimaryPushButton(FIF.ADD, "下载 KiraAI", container)
        add_btn.setToolTip("从 GitHub 下载并安装 KiraAI")
        add_btn.clicked.connect(self._download_kira)
        header.addWidget(add_btn)

        manual_btn = PushButton(FIF.FOLDER, "添加已有", container)
        manual_btn.setToolTip("添加已安装的 KiraAI 实例")
        manual_btn.clicked.connect(self._add_existing)
        header.addWidget(manual_btn)
        layout.addLayout(header)

        # 批量操作
        batch_row = QHBoxLayout()
        batch_row.setSpacing(8)
        start_all_btn = PushButton(FIF.PLAY, "全部启动", container)
        start_all_btn.clicked.connect(self._start_all)
        batch_row.addWidget(start_all_btn)
        stop_all_btn = PushButton(FIF.PAUSE, "全部停止", container)
        stop_all_btn.clicked.connect(self._stop_all)
        batch_row.addWidget(stop_all_btn)
        batch_row.addStretch()
        self.running_label = BodyLabel("运行: 0/0", container)
        batch_row.addWidget(self.running_label)
        layout.addLayout(batch_row)

        # 实例卡片
        self.cards_widget = QWidget(container)
        self.cards_layout = FlowLayout(self.cards_widget)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_widget.setMinimumHeight(100)
        layout.addWidget(self.cards_widget)

        self.empty_hint = BodyLabel(
            '点击「下载 KiraAI」从 GitHub 安装，或「添加已有」选择本地项目', container,
        )
        self.empty_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.empty_hint)

        sep = QFrame(container)
        sep.setFrameShape(QFrame.HLine)
        layout.addWidget(sep)

        # 控制台
        console_header = QHBoxLayout()
        console_header.addWidget(SubtitleLabel("控制台输出", container))
        console_header.addStretch()

        # 实例过滤下拉框
        self.console_filter = QComboBox(container)
        self.console_filter.addItem("全部实例")
        self.console_filter.setFixedWidth(150)
        self.console_filter.currentIndexChanged.connect(self._on_filter_changed)
        console_header.addWidget(self.console_filter)

        clear_btn = PushButton(FIF.DELETE, "清空", container)
        clear_btn.setFixedHeight(BUTTON_HEIGHT_SMALL)
        clear_btn.clicked.connect(lambda: self.console.clear())
        console_header.addWidget(clear_btn)
        self.console_title = BodyLabel("(选择实例查看)", container)
        console_header.addWidget(self.console_title)
        layout.addLayout(console_header)

        self.console = TextBrowser(container)
        self.console.setPlaceholderText("选择实例后点击启动...")
        layout.addWidget(self.console, 1)

        # 日志缓冲区 - 按实例名称存储
        self._log_buffers = {}  # name -> list of lines
        self._current_filter = "全部实例"

        self._im.instances_changed.connect(self._rebuild_cards)
        self._im.instances_changed.connect(self._update_filter_options)
        self._im.any_output.connect(self._on_any_output)

        saved = cfg_get("instances") or []
        if saved:
            for cfg in saved:
                self._im.add(dict(cfg))
        else:
            self._create_default()

        # 启动时检测残留进程
        self._check_orphan_processes()

    def _get_pid_by_port(self, port):
        """根据端口获取占用该端口的进程 PID"""
        import subprocess
        try:
            # Windows: netstat -ano | findstr :端口
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            for line in result.stdout.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    if parts:
                        try:
                            return int(parts[-1])
                        except ValueError:
                            pass
        except Exception as e:
            logger.error(f"获取端口 {port} 的 PID 失败: {e}")
        return None

    def _kill_process_by_pid(self, pid):
        """根据 PID 杀死进程"""
        import subprocess
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            return True
        except Exception as e:
            logger.error(f"杀死进程 {pid} 失败: {e}")
            return False

    def _check_orphan_processes(self):
        """启动时检测残留进程（撞端口检测）"""
        orphan_ports = []
        for inst in self._im.instances():
            port = inst.cfg.get("port", 5267)
            if check_port_open("127.0.0.1", port):
                orphan_ports.append((inst.name, port))

        if not orphan_ports:
            return

        names = ", ".join(f"{name}(:{port})" for name, port in orphan_ports)
        reply = QMessageBox.question(
            self, "检测到残留进程",
            f"检测到以下端口被占用，可能是上次未正常关闭的进程:\n{names}\n\n是否强制停止这些进程？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            for name, port in orphan_ports:
                pid = self._get_pid_by_port(port)
                if pid:
                    if self._kill_process_by_pid(pid):
                        logger.info(f"已停止残留进程: {name} (PID: {pid}, 端口: {port})")
                    else:
                        logger.error(f"停止残留进程失败: {name} (PID: {pid})")
                else:
                    logger.warning(f"未找到占用端口 {port} 的进程")

    def _create_default(self):
        pp = cfg_get("project_path") or ""
        if not pp:
            return  # 无项目路径时不创建空实例
        self._im.add({"name": "KiraAI", "port": 5267, "data_dir": "",
                      "project_path": pp, "extra_args": []})

    # ---- 下载 KiraAI 向导 ----

    def _download_kira(self):
        dlg = DownloadDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return

        target_path, repo_url, route_name, extra_args = dlg.get_result()
        if not target_path or not os.path.exists(target_path):
            return

        # 自动创建 venv + 安装依赖
        self._install_deps_for_path(target_path)
        cfg_set("project_path", target_path)

        # 添加默认实例
        used_ports = {inst.port for inst in self._im.instances()}
        port = 5267
        while port in used_ports:
            port += 1

        name = os.path.basename(target_path) or "KiraAI"
        self._im.add({
            "name": name, "port": port,
            "data_dir": os.path.join(target_path, "data"),
            "project_path": target_path, "extra_args": extra_args,
        })
        self._save()

    def _install_deps_for_path(self, project_path, on_done=None):
        """为指定路径创建 venv 并安装依赖

        流程：
        1. 检查 requirements.txt 是否存在
        2. 计算 venv 路径（始终在项目目录下）
        3. 使用 SetupWorker 创建 venv（如果需要）并安装依赖
        """
        if self._setup_worker and self._setup_worker.isRunning():
            self._setup_worker.terminate()
            self._setup_worker.wait(2000)

        # 检查 requirements.txt
        req = os.path.join(project_path, "requirements.txt")
        if not os.path.exists(req):
            notify_warning("跳过", "找不到 requirements.txt，依赖安装跳过", parent=self)
            return

        # venv 路径始终在项目目录下
        venv_path = os.path.join(project_path, "venv")

        # 确定状态提示文本
        if is_venv(venv_path):
            tip_text = "检查并安装依赖..."
        else:
            tip_text = "创建虚拟环境 + 安装依赖..."

        self._state_tip = StateToolTip("正在配置环境", tip_text, self.window())
        self._state_tip.move(self._state_tip.getSuitablePos())
        self._state_tip.show()

        # 获取镜像配置
        primary, fallback, _ = get_mirror_for_install()

        # 创建 worker 并启动
        self._setup_worker = SetupWorker(venv_path, req, primary, fallback)

        self._setup_worker.progress.connect(self._on_setup_progress)
        self._setup_worker.finished.connect(
            lambda ok, msg: self._on_setup_done(ok, msg, on_done, project_path, venv_path)
        )
        self._setup_worker.start()

    def _on_setup_progress(self, line):
        append_and_scroll(self.console, line)

    def _on_setup_done(self, ok, msg, on_done=None, project_path=None, venv_path=None):
        if self._state_tip:
            self._state_tip.setContent(msg)
            self._state_tip.setState(True)
            self._state_tip = None
        if ok:
            # 更新配置
            if project_path:
                cfg_set("project_path", project_path)
            if venv_path:
                cfg_set("venv_path", venv_path)
            notify_success("环境就绪", msg, parent=self)
            if on_done:
                on_done()
        else:
            notify_error("配置失败", msg, parent=self)

    # ---- 添加已有项目 ----

    def _add_existing(self):
        path = QFileDialog.getExistingDirectory(self, "选择 KiraAI 项目目录")
        if not path:
            return
        if not is_kira_project(path):
            notify_error("无效", "所选目录不是有效的 KiraAI 项目", parent=self)
            return

        name, ok = QInputDialog.getText(self, "实例名称", "名称:", text=os.path.basename(path))
        if not ok or not name.strip():
            return

        used_ports = {inst.port for inst in self._im.instances()}
        port = 5267
        while port in used_ports:
            port += 1

        self._im.add({
            "name": name.strip(), "port": port,
            "data_dir": os.path.join(path, "data"),
            "project_path": path, "extra_args": [],
        })
        self._save()

    # ---- 卡片管理 ----

    def _rebuild_cards(self):
        """增量更新卡片列表 — 实例数不变时仅刷新状态，避免全量销毁重建"""
        try:
            instances = self._im.instances()
            self.empty_hint.setVisible(len(instances) == 0)

            current_ids = {inst.name for inst in instances}
            cached_ids = getattr(self, '_cached_instance_ids', set())

            if current_ids == cached_ids and len(instances) == self.cards_layout.count():
                # 仅状态变化，立即刷新所有卡片的端口检测状态
                for i in range(self.cards_layout.count()):
                    item = self.cards_layout.itemAt(i)
                    if item and isinstance(item.widget(), InstanceCard):
                        item.widget()._check_port_status()
                self._update_running_label()
                return

            # 全量重建
            self._clear_cards()

            for inst in instances:
                card = InstanceCard(inst, self.cards_widget)
                card.selected.connect(self._on_card_selected)
                card.start_clicked.connect(self._on_start)
                card.stop_clicked.connect(self._on_stop)
                card.remove_clicked.connect(self._on_remove)
                card.view_clicked.connect(self._on_view)
                card.config_clicked.connect(self._on_config)
                card.rename_clicked.connect(self._on_rename)
                self.cards_layout.addWidget(card)

            self._cached_instance_ids = current_ids
            self._update_running_label()
            self._save()
        except Exception as e:
            logger.exception("重建实例卡片失败")
            notify_error("界面错误", str(e), parent=self)

    def _clear_cards(self):
        # 通过 FlowLayout 自身的方法移除所有 widget，确保内部 _items 列表同步清空
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item:
                w = item.widget()
                if w:
                    if isinstance(w, InstanceCard):
                        w.cleanup()
                    w.setParent(None)
                    w.deleteLater()
        self._cached_instance_ids = set()

    def _on_card_selected(self, instance):
        self._im.set_active(instance)
        self.console_title.setText(f"当前: {instance.name} (端口:{instance.port})")

    def _refresh_instance_port(self, instance):
        """刷新指定实例卡片的端口显示"""
        for i in range(self.cards_layout.count()):
            item = self.cards_layout.itemAt(i)
            if item and item.widget() and isinstance(item.widget(), InstanceCard):
                card = item.widget()
                if card.inst is instance:
                    card.port_label.setText(f"端口: {instance.port}")
                    break

    def _on_view(self, instance):
        """打开浏览器查看实例 WebUI"""
        w = self.window()
        if w and hasattr(w, "browser_page"):
            w.browser_page.open_for_instance(instance)
            w.switchToQWidget("browserPage")
        else:
            import webbrowser
            webbrowser.open(f"http://localhost:{instance.port}")

    def _on_config(self, instance):
        """打开框架配置编辑弹窗"""
        dlg = ConfigDialog(instance, self)
        dlg.exec_()
        # 配置对话框关闭后，刷新卡片的端口显示
        self._refresh_instance_port(instance)

    def _on_rename(self, instance):
        """重命名实例"""
        old_name = instance.name
        new_name, ok = QInputDialog.getText(
            self, "重命名实例", "输入新名称:", text=old_name,
        )
        if ok and new_name and new_name != old_name:
            # 检查名称是否重复
            for inst in self._im.instances():
                if inst.name == new_name and inst is not instance:
                    notify_warning("提示", f"名称 '{new_name}' 已存在", parent=self)
                    return
            # 更新名称
            instance.name = new_name
            # 更新日志缓冲区
            if old_name in self._log_buffers:
                self._log_buffers[new_name] = self._log_buffers.pop(old_name)
            # 更新卡片显示
            for i in range(self.cards_layout.count()):
                item = self.cards_layout.itemAt(i)
                if item:
                    card = item.widget()
                    if isinstance(card, InstanceCard) and card.inst is instance:
                        card.name_label.setText(new_name)
                        break
            # 更新过滤下拉框
            self._update_filter_options()
            # 保存配置
            self._save()
            notify_success("已重命名", f"{old_name} → {new_name}", parent=self)

    # ---- 启动/停止 (含强制依赖检查) ----

    def _on_start(self, instance):
        try:
            project_path = instance.project_path or cfg_get("project_path")
            if not project_path:
                notify_warning("提示", "请在项目管理页设置项目路径", parent=self)
                return
            if not os.path.exists(os.path.join(project_path, "main.py")):
                notify_error("错误", f"项目不完整，缺少 main.py", parent=self)
                return

            # venv 路径始终在项目目录下
            venv_path = os.path.join(project_path, "venv")

            # 检查 venv 是否存在且有效
            if not is_venv(venv_path):
                reply = QMessageBox.question(
                    self, "环境未就绪",
                    "虚拟环境尚未创建。\n\n是否创建 venv 并安装依赖？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    self._install_deps_for_path(
                        project_path,
                        on_done=lambda: self._do_start(instance, project_path, venv_path),
                    )
                return

            # 更新配置
            cfg_set("project_path", project_path)
            cfg_set("venv_path", venv_path)

            # 检查依赖
            deps_ok, missing, _ = check_dependencies_installed(
                venv_path, os.path.join(project_path, "requirements.txt"),
            )
            if not deps_ok:
                reply = QMessageBox.question(
                    self, "依赖未安装",
                    f"缺失 {len(missing)} 个依赖包。\n\n是否立即安装？",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    self._install_deps_for_path(
                        project_path,
                        on_done=lambda: self._do_start(instance, project_path, venv_path),
                    )
                return

            self._do_start(instance, project_path, venv_path)
        except Exception as e:
            logger.exception(f"启动失败: {instance.name if instance else 'unknown'}")
            notify_error("启动失败", str(e), parent=self)

    def _do_start(self, instance, project_path, venv_path):
        """实际启动实例（由 _on_start 或依赖安装完成后调用）"""
        python = get_venv_python(venv_path)
        instance.cfg["project_path"] = project_path
        instance.start(python)
        self._update_running_label()
        logger.info(f"实例已启动: {instance.name} (端口:{instance.port}, 路径:{project_path})")

        notify_info("已启动", f"{instance.name} — 点击「查看」打开 WebUI", parent=self)

    def _on_stop(self, instance):
        try:
            instance.stop()
            self._update_running_label()
            logger.info(f"实例已停止: {instance.name}")
        except Exception as e:
            logger.exception(f"停止实例失败: {instance.name}")
            notify_error("停止失败", str(e), parent=self)

    def _on_remove(self, instance):
        # 创建自定义对话框，包含删除文件选项
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("确认删除")
        msg_box.setText(f'确定要删除实例 "{instance.name}" 吗？\n运行中的进程将先被停止。')
        msg_box.setInformativeText("项目文件默认保留，勾选后将一并删除。")
        msg_box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        msg_box.setDefaultButton(QMessageBox.No)

        # 添加删除文件复选框
        delete_files_cb = QCheckBox("同时删除项目文件", msg_box)
        delete_files_cb.setToolTip("删除项目目录及其所有内容（不可恢复）")
        msg_box.setCheckBox(delete_files_cb)

        reply = msg_box.exec_()
        if reply == QMessageBox.Yes:
            # 先停止实例
            if instance.is_running():
                instance.stop()

            # 如果勾选了删除文件，执行删除
            if delete_files_cb.isChecked():
                project_path = instance.project_path
                if project_path and os.path.isdir(project_path):
                    try:
                        shutil.rmtree(project_path, onerror=_remove_readonly)
                        logger.info(f"已删除项目目录: {project_path}")
                        notify_success("已删除", f"项目目录已删除: {project_path}", parent=self)
                    except Exception as e:
                        logger.exception(f"删除项目目录失败: {project_path}")
                        notify_error("删除失败", f"无法删除项目目录: {e}", parent=self)
                else:
                    notify_warning("提示", "项目目录不存在，跳过文件删除", parent=self)

            # 从实例列表中移除
            self._im.remove_by_name(instance.name)
            self._save()

    def _start_all(self):
        for inst in self._im.instances():
            if not inst.is_running():
                self._on_start(inst)

    def _stop_all(self):
        for inst in self._im.instances():
            if inst.is_running():
                inst.stop()

    def _update_running_label(self):
        total = self._im.count()
        running = self._im.running_count()
        self.running_label.setText(f"运行: {running}/{total}")
        self._notify_home()

    def _on_any_output(self, line):
        # 解析实例名称 [实例名] 内容
        inst_name = None
        display_line = line
        if line.startswith("[") and "]" in line:
            bracket_end = line.index("]")
            inst_name = line[1:bracket_end]
            display_line = line[bracket_end + 2:]  # 去掉 "[name] "

        # 存储到缓冲区
        if inst_name:
            if inst_name not in self._log_buffers:
                self._log_buffers[inst_name] = []
            self._log_buffers[inst_name].append(display_line)
            # 限制缓冲区大小
            if len(self._log_buffers[inst_name]) > 5000:
                self._log_buffers[inst_name] = self._log_buffers[inst_name][-3000:]
        else:
            # 没有实例标识的通用日志
            if "通用" not in self._log_buffers:
                self._log_buffers["通用"] = []
            self._log_buffers["通用"].append(display_line)

        # 根据过滤条件显示
        if self._current_filter == "全部实例":
            append_and_scroll(self.console, display_line)
        elif inst_name and self._current_filter == inst_name:
            append_and_scroll(self.console, display_line)

    def _on_filter_changed(self, index):
        """切换日志过滤"""
        self._current_filter = self.console_filter.currentText()
        # 重新加载对应实例的日志
        self.console.clear()
        if self._current_filter == "全部实例":
            for name, lines in self._log_buffers.items():
                for line in lines[-100:]:  # 显示最后100行
                    append_and_scroll(self.console, line)
        elif self._current_filter in self._log_buffers:
            for line in self._log_buffers[self._current_filter][-100:]:
                append_and_scroll(self.console, line)

    def _update_filter_options(self):
        """更新过滤下拉框选项"""
        current = self.console_filter.currentText()
        self.console_filter.clear()
        self.console_filter.addItem("全部实例")
        for inst in self._im.instances():
            self.console_filter.addItem(inst.name)
        # 恢复之前的选择
        idx = self.console_filter.findText(current)
        if idx >= 0:
            self.console_filter.setCurrentIndex(idx)

    def _save(self):
        cfg = cfg_full()
        cfg["instances"] = self._im.to_config_list()
        save_full(cfg)

    def _notify_home(self):
        w = self.window()
        if w and hasattr(w, "home_page"):
            w.home_page.update_running_status(self._im.running_count())
