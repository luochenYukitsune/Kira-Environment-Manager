"""KiraAI 框架配置编辑器 — 弹窗模式"""

import json
import os
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QInputDialog, QDialog,
)

from qfluentwidgets import (
    SettingCardGroup, PushSettingCard,
    BodyLabel, SubtitleLabel,
    FluentIcon as FIF, PrimaryPushButton,
)

from kira_env_manager.utils.logger import logger
from kira_env_manager.common.config import get as cfg_get, full as cfg_full, save_full


class ConfigDialog(QDialog):
    def __init__(self, instance, parent=None):
        super().__init__(parent)
        self.instance = instance
        self._webui_path = ""
        self._webui_config = {"host": "0.0.0.0", "port": 5267}
        self._cards = {}  # key -> widget

        name = instance.cfg.get("name", "Unknown")
        self.setWindowTitle(f"KiraAI 配置 — {name}")
        self.resize(480, 320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # 滚动区
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget(scroll)
        scroll.setWidget(container)
        clayout = QVBoxLayout(container)
        clayout.setContentsMargins(24, 12, 24, 12)
        clayout.setSpacing(10)

        clayout.addWidget(SubtitleLabel(f"框架配置 — {name}", container))
        self.path_label = BodyLabel("", container)
        clayout.addWidget(self.path_label)

        # --- WebUI (webui.json) ---
        g1 = SettingCardGroup("WebUI 端口 & 地址", container)
        self._webui_str("host", FIF.GLOBE, "绑定地址", "0.0.0.0 = 所有网卡, 127.0.0.1 = 仅本机", g1)
        self._webui_int("port", FIF.LINK, "端口", "WebUI 监听端口", 1024, 65535, g1)
        clayout.addWidget(g1)

        clayout.addStretch(1)
        layout.addWidget(scroll, 1)

        # 底部按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        done_btn = PrimaryPushButton(FIF.ACCEPT, "完成", self)
        done_btn.clicked.connect(self.accept)
        btn_row.addWidget(done_btn)
        layout.addLayout(btn_row)

        self._load_config()

    # ---- 配置 I/O ----

    def _load_config(self):
        data_dir = self.instance.cfg.get("data_dir", "")
        if not data_dir:
            pp = self.instance.cfg.get("project_path", "") or cfg_get("project_path")
            data_dir = os.path.join(pp, "data") if pp else ""

        # 加载 webui.json
        self._webui_path = os.path.join(data_dir, "webui.json")
        if os.path.exists(self._webui_path):
            try:
                with open(self._webui_path, "r", encoding="utf-8") as f:
                    self._webui_config = json.load(f)
            except Exception as e:
                logger.warning(f"读取 webui.json 失败 ({self._webui_path}): {e}")
        else:
            self._webui_config = {"host": "0.0.0.0", "port": 5267}

        self.path_label.setText(f"{os.path.basename(data_dir)}  —  webui.json")
        self._refresh_all()

    def _save_webui(self):
        if not self._webui_path:
            return
        try:
            # 写入前确保目录存在
            os.makedirs(os.path.dirname(self._webui_path), exist_ok=True)
            with open(self._webui_path, "w", encoding="utf-8") as f:
                json.dump(self._webui_config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"写入 webui.json 失败 ({self._webui_path}): {e}")

    # ---- 控件工厂 ----

    def _webui_str(self, key, icon, title, hint, group):
        val = self._webui_config.get(key, "")
        c = PushSettingCard("编辑", icon, title, hint, group)
        c.setContent(str(val) if val else "(空)")
        c.clicked.connect(lambda k=key: self._edit_webui_str(k))
        group.addSettingCard(c)
        self._cards[key] = c

    def _webui_int(self, key, icon, title, hint, lo, hi, group):
        try:
            val = int(self._webui_config.get(key, lo))
        except (ValueError, TypeError):
            val = lo
        c = PushSettingCard("编辑", icon, title, hint, group)
        c.setContent(str(val))
        c.clicked.connect(lambda k=key, l=lo, h=hi: self._edit_webui_int(k, l, h))
        group.addSettingCard(c)
        self._cards[key] = c

    # ---- 编辑方法 ----

    def _edit_webui_str(self, key):
        cur = str(self._webui_config.get(key, ""))
        text, ok = QInputDialog.getText(self, "编辑 webui.json", key, text=cur)
        if ok:
            self._webui_config[key] = text.strip()
            self._save_webui()
            if key in self._cards:
                self._cards[key].setContent(text.strip() or "(空)")

    def _edit_webui_int(self, key, lo, hi):
        cur = int(self._webui_config.get(key, lo))
        val, ok = QInputDialog.getInt(self, "编辑 webui.json", f"{key} ({lo}-{hi}):", cur, lo, hi)
        if ok:
            self._webui_config[key] = val
            self._save_webui()
            if key in self._cards:
                self._cards[key].setContent(str(val))
            # 同步更新 instance.cfg 中的端口，使 InstanceCard 显示更新
            if key == "port" and self.instance:
                self.instance.cfg["port"] = val
                # 新增: 通知卡片刷新端口显示和状态检测
                self.instance.port_changed.emit(val)
                # 持久化到 manager_config.json
                self._save_instance_config()

    # ---- 刷新 ----

    def _refresh_all(self):
        for key in ["host", "port"]:
            if key in self._cards:
                val = self._webui_config.get(key, "")
                self._cards[key].setContent(str(val))

    def _save_instance_config(self):
        """将实例配置持久化到 manager_config.json"""
        try:
            cfg = cfg_full()
            instances = cfg.get("instances", [])
            # 找到并更新对应的实例
            for i, inst in enumerate(instances):
                if inst.get("name") == self.instance.cfg.get("name"):
                    instances[i] = self.instance.cfg.copy()
                    break
            cfg["instances"] = instances
            save_full(cfg)
        except Exception as e:
            logger.warning(f"保存实例配置失败: {e}")
