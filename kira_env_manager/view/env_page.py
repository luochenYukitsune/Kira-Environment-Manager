"""环境配置页 - Python 检测、镜像选择、venv 创建、依赖安装、字体设置"""

import os
from pathlib import Path
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFontDatabase
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog, QScrollArea, QInputDialog,
    QMessageBox,
)

from qfluentwidgets import (
    SettingCardGroup, PushSettingCard, HyperlinkButton,
    StateToolTip, BodyLabel, SubtitleLabel,
    TextBrowser, FluentIcon as FIF,
)

from kira_env_manager.utils.python_env import (
    detect_python, get_python_download_urls, create_venv,
    install_requirements, is_venv, check_dependencies_installed,
)
from kira_env_manager.utils.pip_mirrors import (
    MIRRORS, test_all_mirrors, safe_mirror_index,
)
from kira_env_manager.utils.helpers import append_and_scroll, get_mirror_for_install
from kira_env_manager.utils.logger import (
    logger, notify_info, notify_success, notify_warning, notify_error,
)
from kira_env_manager.common.config import get as cfg_get, set_config as cfg_set
from kira_env_manager.common.constants import PAGE_MARGINS


class VenvWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, venv_path):
        super().__init__()
        self.venv_path = venv_path

    def run(self):
        ok, msg = create_venv(self.venv_path)
        self.finished.emit(ok, msg)


class MirrorTestWorker(QThread):
    """后台测速"""
    progress = pyqtSignal(str)
    finished = pyqtSignal(int, str, str)  # best_index, name, url

    def run(self):
        self.progress.emit("正在测试镜像源速度...\n")
        results = test_all_mirrors(
            callback=lambda n, u, l: self.progress.emit(
                f"  {n}: {'%.0f ms' % l if l else '超时'}\n"
            )
        )
        if results and results[0][2] is not None:
            best_name, best_url, best_latency = results[0]
            best_idx = next(
                (i for i, (n, _, _) in enumerate(MIRRORS) if n == best_name), 0
            )
        else:
            best_idx, best_name, best_url, best_latency = 0, MIRRORS[0][0], MIRRORS[0][1], None
        self.progress.emit(
            f"\n>>> 最快: {best_name}"
            + (f" ({'%.0f' % best_latency} ms)" if best_latency else " (默认)")
            + "\n"
        )
        self.finished.emit(best_idx, best_name, best_url)


class InstallWorker(QThread):
    line_output = pyqtSignal(str)
    finished = pyqtSignal(bool, str)

    def __init__(self, venv_path, req_path, mirror_url, fallback_mirrors):
        super().__init__()
        self.venv_path = venv_path
        self.req_path = req_path
        self.mirror_url = mirror_url
        self.fallback_mirrors = fallback_mirrors

    def run(self):
        ok, msg = install_requirements(
            self.venv_path,
            self.req_path,
            mirror_url=self.mirror_url,
            fallback_mirrors=self.fallback_mirrors,
            output_callback=lambda line: self.line_output.emit(line),
        )
        self.finished.emit(ok, msg)


class EnvPage(QScrollArea):

    _dep_status_label = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("envPage")
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._worker = None
        self._tooltip = None

        container = QWidget(self)
        self.setWidget(container)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(*PAGE_MARGINS)
        layout.setSpacing(16)

        header = QHBoxLayout()
        header.addWidget(SubtitleLabel("环境配置", container))
        header.addStretch()
        layout.addLayout(header)

        # === Python 检测 ===
        self.python_group = SettingCardGroup("Python 环境", container)

        self.python_card = PushSettingCard(
            "检测", FIF.CODE, "Python 解释器",
            "点击检测", self.python_group,
        )
        self.python_card.clicked.connect(self._detect_python)
        self.python_group.addSettingCard(self.python_card)

        layout.addWidget(self.python_group)

        self.download_widget = QWidget(container)
        dl = QVBoxLayout(self.download_widget)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(4)
        dl.addWidget(BodyLabel("如未安装 Python，可从以下地址下载 (需 Python 3.10+):", container))
        for name, url in get_python_download_urls():
            dl.addWidget(HyperlinkButton(url, name, container))
        layout.addWidget(self.download_widget)
        self.download_widget.setVisible(False)

        # === pip 镜像 ===
        self.mirror_group = SettingCardGroup("pip 镜像源", container)

        current_mirror = safe_mirror_index(cfg_get("mirror_index") or 0)
        mirror_name = MIRRORS[current_mirror][0]

        self.mirror_card = PushSettingCard(
            "切换", FIF.SYNC, "pip 镜像源",
            f"{mirror_name}  -  点击切换", self.mirror_group,
        )
        self.mirror_card.clicked.connect(self._choose_mirror)
        self.mirror_group.addSettingCard(self.mirror_card)

        self.speedtest_card = PushSettingCard(
            "测速", FIF.SPEED_HIGH, "自动测速",
            "测试所有镜像源，选择最快的", self.mirror_group,
        )
        self.speedtest_card.clicked.connect(self._speed_test)
        self.mirror_group.addSettingCard(self.speedtest_card)

        layout.addWidget(self.mirror_group)

        # === venv ===
        self.venv_group = SettingCardGroup("虚拟环境", container)

        self.venv_card = PushSettingCard(
            "创建", FIF.FOLDER, "虚拟环境",
            "尚未创建", self.venv_group,
        )
        self.venv_card.clicked.connect(self._create_venv)
        self.venv_group.addSettingCard(self.venv_card)

        self.venv_select_card = PushSettingCard(
            "选择", FIF.FOLDER, "使用已有 venv",
            "选择已有虚拟环境目录", self.venv_group,
        )
        self.venv_select_card.clicked.connect(self._select_venv)
        self.venv_group.addSettingCard(self.venv_select_card)

        layout.addWidget(self.venv_group)

        # === 依赖安装 ===
        self.deps_group = SettingCardGroup("依赖安装", container)

        self.install_card = PushSettingCard(
            "安装", FIF.DOWNLOAD, "安装 requirements.txt",
            "在虚拟环境中安装项目依赖", self.deps_group,
        )
        self.install_card.clicked.connect(self._install_deps)
        self.deps_group.addSettingCard(self.install_card)

        # 依赖状态标签
        self._dep_status_label = BodyLabel("", container)
        self._dep_status_label.setVisible(False)
        layout.addWidget(self._dep_status_label)

        layout.addWidget(self.deps_group)

        # === 字体设置 ===
        self.font_group = SettingCardGroup("字体设置", container)

        current_font_path = cfg_get("font_path") or ""
        if current_font_path:
            font_hint = Path(current_font_path).name
        else:
            font_hint = "HarmonyOS Sans（内置默认）"

        self.font_card = PushSettingCard(
            "选择字体", FIF.FONT, "当前字体",
            font_hint, self.font_group,
        )
        self.font_card.clicked.connect(self._choose_font)
        self.font_group.addSettingCard(self.font_card)

        self.font_reset_card = PushSettingCard(
            "重置", FIF.DELETE, "恢复默认字体",
            "清除自定义字体配置，使用内置默认字体", self.font_group,
        )
        self.font_reset_card.clicked.connect(self._reset_font)
        self.font_group.addSettingCard(self.font_reset_card)

        layout.addWidget(self.font_group)

        # 输出控制台
        self.console = TextBrowser(container)
        self.console.setPlaceholderText("操作输出将显示在这里...")
        self.console.setMaximumHeight(250)
        self.console.setMinimumHeight(140)
        layout.addWidget(self.console)

        layout.addStretch(1)

        self._auto_detect()
        self._refresh_dep_status()

    def _refresh_dep_status(self):
        """刷新依赖状态显示"""
        project_path = cfg_get("project_path")
        venv_path = cfg_get("venv_path")
        if not project_path or not venv_path or not is_venv(venv_path):
            if self._dep_status_label:
                self._dep_status_label.setVisible(False)
            return

        req_path = os.path.join(project_path, "requirements.txt")
        if not os.path.exists(req_path):
            if self._dep_status_label:
                self._dep_status_label.setVisible(False)
            return

        all_ok, missing, msg = check_dependencies_installed(venv_path, req_path)
        if self._dep_status_label:
            if all_ok:
                self._dep_status_label.setText("✅ 依赖全部已安装")
                self._dep_status_label.setStyleSheet("color: #4caf50;")
            else:
                count = len(missing)
                self._dep_status_label.setText(f"⚠️ 缺失 {count} 个依赖: {', '.join(missing[:5])}{'…' if count > 5 else ''}")
                self._dep_status_label.setStyleSheet("color: #f44336;")
            self._dep_status_label.setVisible(True)

    def showEvent(self, event):
        super().showEvent(event)
        venv_path = cfg_get("venv_path")
        if venv_path and is_venv(venv_path):
            self.venv_card.setTitle("虚拟环境已就绪")
            self.venv_card.setContent(venv_path)
        else:
            self.venv_card.setTitle("创建虚拟环境")
            self.venv_card.setContent("venv 目录不存在，将在安装时创建")
        self._refresh_dep_status()

    def _auto_detect(self):
        v, p = detect_python()
        if v:
            self.python_card.setContent(f"Python {v}  ({p})")
            self.download_widget.setVisible(False)
        else:
            self.python_card.setTitle("未检测到 Python")
            self.python_card.setContent("请安装 Python 3.10+")
            self.download_widget.setVisible(True)

    def _detect_python(self):
        v, p = detect_python()
        if v:
            self.python_card.setContent(f"Python {v}  ({p})")
            self.download_widget.setVisible(False)
            notify_success("Python 已检测", f"版本: {v}\n路径: {p}", parent=self)
        else:
            self.python_card.setTitle("未检测到 Python")
            self.python_card.setContent("请安装 Python 3.10+")
            self.download_widget.setVisible(True)
            notify_warning("未检测到 Python", "请先安装 Python 3.10+", parent=self)

    def _choose_font(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择字体文件", "",
            "TrueType 字体 (*.ttf);;所有文件 (*)",
        )
        if not path:
            return
        font_id = QFontDatabase.addApplicationFont(path)
        if font_id < 0:
            notify_error("无效字体", "所选文件不是有效的 TrueType 字体", parent=self)
            return
        family = QFontDatabase.applicationFontFamilies(font_id)[0]
        cfg_set("font_path", path)
        self.font_card.setContent(Path(path).name)
        notify_success("字体已设置", f"已切换到: {family}\n重启应用后生效", parent=self, duration=4000)

    def _reset_font(self):
        cfg_set("font_path", "")
        self.font_card.setContent("HarmonyOS Sans（内置默认）")
        notify_info("字体已重置", "已恢复内置默认字体，重启应用后生效", parent=self, duration=3000)

    def _choose_mirror(self):
        items = [f"{m[0]}  -  {m[2]}" for m in MIRRORS]
        current = safe_mirror_index(cfg_get("mirror_index") or 0)
        item, ok = QInputDialog.getItem(
            self, "选择镜像源", "选择 pip 安装源:", items, current, False,
        )
        if ok and item:
            idx = items.index(item)
            cfg_set("mirror_index", idx)
            name = MIRRORS[idx][0]
            self.mirror_card.setContent(f"{name}  -  点击切换")
            notify_info("镜像源已切换", f"当前: {name}", parent=self, duration=2000)

    def _speed_test(self):
        self.console.clear()
        self.speedtest_card.setEnabled(False)
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        self._tooltip = StateToolTip("正在测速", "测试各镜像源响应...", self.window())
        self._tooltip.move(self._tooltip.getSuitablePos())
        self._tooltip.show()
        self._worker = MirrorTestWorker()
        self._worker.progress.connect(self._on_speed_progress)
        self._worker.finished.connect(self._on_speed_done)
        self._worker.start()

    def _on_speed_progress(self, line):
        append_and_scroll(self.console, line)

    def _on_speed_done(self, best_idx, best_name, best_url):
        self.speedtest_card.setEnabled(True)
        if self._tooltip:
            self._tooltip.setContent(f"最快: {best_name}")
            self._tooltip.setState(True)
            self._tooltip = None
        cfg_set("mirror_index", best_idx)
        self.mirror_card.setContent(f"{best_name}  -  点击切换")
        notify_success("测速完成", f"已自动选择: {best_name}", parent=self)

    def _create_venv(self):
        project_path = cfg_get("project_path")
        if not project_path:
            notify_warning("提示", "请先在项目管理页设置项目路径", parent=self)
            return
        venv_path = os.path.join(project_path, "venv")
        if os.path.exists(venv_path):
            notify_warning("提示", f"虚拟环境已存在: {venv_path}", parent=self)
            return
        self.venv_card.setEnabled(False)
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        self._tooltip = StateToolTip("正在创建虚拟环境", "请稍候...", self.window())
        self._tooltip.move(self._tooltip.getSuitablePos())
        self._tooltip.show()
        self._worker = VenvWorker(venv_path)
        self._worker.finished.connect(self._on_venv_created)
        self._worker.start()

    def _on_venv_created(self, ok, msg):
        self.venv_card.setEnabled(True)
        if self._tooltip:
            self._tooltip.setContent(msg)
            self._tooltip.setState(True)
            self._tooltip = None
        if ok:
            venv_path = os.path.join(cfg_get("project_path") or "", "venv")
            if not cfg_get("venv_path"):
                cfg_set("venv_path", venv_path)
            self.venv_card.setTitle("虚拟环境已就绪")
            self.venv_card.setContent(venv_path)
            notify_success("成功", msg, parent=self)
        else:
            logger.error(f"venv 创建失败: {msg}")
            notify_error("失败", msg, parent=self)
        self._refresh_dep_status()

    def _select_venv(self):
        path = QFileDialog.getExistingDirectory(self, "选择虚拟环境目录")
        if not path:
            return
        if is_venv(path):
            cfg_set("venv_path", path)
            self.venv_card.setTitle("虚拟环境已就绪")
            self.venv_card.setContent(path)
            notify_success("已设置", f"使用虚拟环境: {path}", parent=self)
        else:
            notify_error("无效", "所选目录不是有效的虚拟环境", parent=self)
        self._refresh_dep_status()

    def _validate_env(self, project_path, venv_path):
        if not project_path:
            notify_warning("提示", "请先在项目管理页设置项目路径", parent=self)
            return False
        if not venv_path or not is_venv(venv_path):
            notify_warning("提示", "请先创建或选择虚拟环境", parent=self)
            return False
        req_path = os.path.join(project_path, "requirements.txt")
        if not os.path.exists(req_path):
            notify_error("错误", f"找不到: {req_path}", parent=self)
            return False
        return req_path

    def _choose_mirror_for_install(self):
        reply = QMessageBox.question(
            self, "选择镜像源",
            "如何选择 pip 镜像源？\n\n"
            "「是」= 使用当前配置的镜像\n"
            "「否」= 手动选择镜像",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Cancel:
            return None
        if reply == QMessageBox.No:
            items = [f"{m[0]}  -  {m[2]}" for m in MIRRORS]
            current = safe_mirror_index(cfg_get("mirror_index") or 0)
            item, ok = QInputDialog.getItem(
                self, "选择镜像源", "选择 pip 安装源:", items, current, False,
            )
            if not ok or not item:
                return None
            idx = items.index(item)
            primary = MIRRORS[idx][1]
            fallback = [m[1] for i, m in enumerate(MIRRORS) if i != idx]
            mirror_name = MIRRORS[idx][0]
        else:
            primary, fallback, mirror_name = get_mirror_for_install()
        return primary, fallback, mirror_name

    def _install_deps(self):
        project_path = cfg_get("project_path")
        venv_path = cfg_get("venv_path")
        req_path = self._validate_env(project_path, venv_path)
        if not req_path:
            return
        mirror = self._choose_mirror_for_install()
        if not mirror:
            return
        primary, fallback, mirror_name = mirror
        self.console.clear()
        self.console.append(f">>> 使用镜像: {mirror_name}\n")
        self.install_card.setEnabled(False)
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        self._tooltip = StateToolTip("正在安装依赖", "请稍候...", self.window())
        self._tooltip.move(self._tooltip.getSuitablePos())
        self._tooltip.show()
        self._worker = InstallWorker(venv_path, req_path, primary, fallback)
        self._worker.line_output.connect(self._on_line)
        self._worker.finished.connect(self._on_install_done)
        self._worker.start()

    def _on_line(self, line):
        append_and_scroll(self.console, line)

    def _on_install_done(self, ok, msg):
        self.install_card.setEnabled(True)
        if self._tooltip:
            self._tooltip.setContent(msg)
            self._tooltip.setState(True)
            self._tooltip = None
        if ok:
            notify_success("成功", msg, parent=self)
            # 通知启动管理页刷新卡片依赖状态
            try:
                w = self.window()
                if w and hasattr(w, "launch_page"):
                    w.launch_page._refresh_all_cards_deps()
            except Exception:
                pass
        else:
            logger.error(f"依赖安装失败: {msg}")
            notify_error("失败", msg, parent=self)
        self._refresh_dep_status()