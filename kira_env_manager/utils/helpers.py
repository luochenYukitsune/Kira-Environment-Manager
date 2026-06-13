"""UI 公共工具 — 控制台滚动、镜像选择、色彩常量、端口检测"""

import socket
from enum import Enum

from qfluentwidgets import isDarkTheme, StateToolTip


def scroll_console_to_bottom(console):
    """将 TextBrowser 滚动到最底部"""
    try:
        c = console.textCursor()
        c.movePosition(c.MoveOperation.End)
        console.setTextCursor(c)
    except Exception:
        pass


def append_and_scroll(console, text):
    """向 TextBrowser 追加文本并滚动到底部

    使用 insertPlainText 追加到末尾，避免 html.escape 对 < > & 等
    正常输出字符的意外转义。
    """
    # 移到文档末尾后插入纯文本
    cursor = console.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cursor.insertText(text.rstrip() + "\n")
    scroll_console_to_bottom(console)


def get_mirror_for_install():
    """读取配置中的镜像设置，返回 (primary_url, fallback_urls, name) 用于依赖安装"""
    from kira_env_manager.common.config import get as cfg_get
    from kira_env_manager.utils.pip_mirrors import MIRRORS, get_mirror_url, get_mirror_name

    mirror_idx = cfg_get("mirror_index")
    primary = get_mirror_url(mirror_idx)
    fallback = [m[1] for i, m in enumerate(MIRRORS) if i != mirror_idx]
    name = get_mirror_name(mirror_idx)
    return primary, fallback, name


def build_clone_url_from_results(results, repo):
    """从测速结果构建最快的 clone URL"""
    from kira_env_manager.utils.network import GITHUB_ROUTES, convert_to_clone_url

    if not results:
        return f"https://github.com/{repo}.git", "直连"

    best_name = results[0][0]
    for route in GITHUB_ROUTES:
        if route[0] == best_name:
            return convert_to_clone_url(route, repo), best_name

    return f"https://github.com/{repo}.git", "直连"


def get_project_path_fallback():
    """自动检测当前 KiraAI 项目路径（供多处复用）"""
    import os
    from kira_env_manager.common.config import get as cfg_get

    project_path = cfg_get("project_path")
    if project_path:
        return project_path

    current = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from kira_env_manager.utils.project import is_kira_project
    if is_kira_project(current):
        return current
    return ""


def status_color(running_or_ok, dark=None):
    """根据状态返回合适的颜色：ok=绿色, warn=黄色, err=红色, neutral=灰色"""
    if dark is None:
        dark = isDarkTheme()

    if running_or_ok is True:
        return "#81c784" if dark else "#4caf50"
    elif running_or_ok is False:
        return "#e57373" if dark else "#f44336"
    elif running_or_ok == "warn":
        return "#fdd835" if dark else "#f9a825"
    else:
        return "#9e9e9e" if dark else "#888"


def check_port_open(host, port, timeout=0.3):
    """检查端口是否开放（跨模块复用）"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def create_state_tooltip(title, content, parent):
    """创建并显示 StateToolTip，返回实例（调用方负责 .setContent / .setState）"""
    tip = StateToolTip(title, content, parent.window() if hasattr(parent, 'window') else parent)
    tip.move(tip.getSuitablePos())
    tip.show()
    return tip


class InstanceState(Enum):
    """KiraInstance 状态机"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    ERROR = "error"


def state_color(state: InstanceState, dark=None):
    """InstanceState → 颜色值（用于状态圆点）"""
    if dark is None:
        from qfluentwidgets import isDarkTheme
        dark = isDarkTheme()

    mapping = {
        InstanceState.IDLE:     "#9e9e9e" if not dark else "#9e9e9e",
        InstanceState.STARTING: "#fdd835" if not dark else "#fdd835",
        InstanceState.RUNNING:  "#4caf50" if not dark else "#81c784",
        InstanceState.STOPPING: "#fdd835" if not dark else "#fdd835",
        InstanceState.ERROR:    "#f44336" if not dark else "#e57373",
    }
    return mapping.get(state, "#9e9e9e")
