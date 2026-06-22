"""UI 公共工具 — 控制台滚动、镜像选择、色彩常量、端口检测"""

import re
import socket
from enum import Enum

from qfluentwidgets import isDarkTheme, StateToolTip

import sys
import threading
import subprocess
from typing import Callable, Tuple, List, Optional

CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def strip_ansi(text: str) -> str:
    """过滤 ANSI 转义码（颜色/样式控制序列）"""
    return _ANSI_RE.sub('', text)


def scroll_console_to_bottom(console):
    """将 TextBrowser 滚动到最底部"""
    try:
        c = console.textCursor()
        c.movePosition(c.MoveOperation.End)
        console.setTextCursor(c)
    except Exception:
        pass


def append_and_scroll(console, text):
    """向 TextBrowser 追加文本（自动过滤 ANSI 转义码）并滚动到底部"""
    clean = strip_ansi(text)
    cursor = console.textCursor()
    cursor.movePosition(cursor.MoveOperation.End)
    cursor.insertText(clean.rstrip() + "\n")
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

    # 仅采用可达(延迟非 None)的线路；全部不可达时回退直连，避免把超时线路当最快
    reachable = [r for r in (results or []) if r[1] is not None]
    if not reachable:
        return f"https://github.com/{repo}.git", "直连"

    best_name = reachable[0][0]
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


def check_port_open(host, port, timeout=0.1):
    """检查端口是否开放（跨模块复用）—— localhost 通常 <1ms，100ms 足够"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, TimeoutError, OSError):
        return False


def _pid_state_file():
    from kira_env_manager.common.constants import get_app_data_dir
    return get_app_data_dir() / "running_pids.json"


_pid_lock = threading.Lock()


def _coerce_positive_pid(pid):
    """将值归一化为正整数 PID；非法/<=0 返回 None。

    关键安全考量：POSIX 上 os.kill(0, sig) 会把信号发给整个进程组（含本程序自身），
    os.kill(-pid, sig) 发给进程组——若持久化文件损坏成 0/负数会误杀。"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    return pid if pid > 0 else None


def read_running_pids() -> dict:
    """读取上次会话持久化的 {port(str): pid} 映射；文件缺失/损坏返回空。"""
    import json
    try:
        with _pid_lock:
            f = _pid_state_file()
            if not f.exists():
                return {}
            data = json.loads(f.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {}
            parsed = {}
            for k, v in data.items():
                pid = _coerce_positive_pid(v)
                if pid is not None:
                    parsed[str(k)] = pid
            return parsed
    except Exception:
        return {}


def _write_running_pids(data: dict):
    import json
    try:
        with _pid_lock:
            f = _pid_state_file()
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass


def record_running_pid(port, pid):
    """记录某端口对应的进程 PID，供下次启动检测残留进程。"""
    if not pid:
        return
    data = read_running_pids()
    data[str(port)] = int(pid)
    _write_running_pids(data)


def clear_running_pid(port):
    """进程正常结束时清除持久化的 PID 记录。"""
    data = read_running_pids()
    if data.pop(str(port), None) is not None:
        _write_running_pids(data)


def kill_pid(pid):
    """按 PID 终止进程树（精确，不依赖端口反查，避免误杀）。返回是否确实终止成功。"""
    import os
    pid = _coerce_positive_pid(pid)
    if pid is None:
        return False
    try:
        if os.name == 'nt':
            result = subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                capture_output=True, creationflags=CREATE_NO_WINDOW, timeout=5,
            )
            return result.returncode == 0
        else:
            import signal as _signal
            os.kill(pid, _signal.SIGTERM)
            return True
    except Exception:
        return False


def pid_alive(pid):
    """判断 PID 是否仍存活（跨平台，尽力而为）。"""
    import os
    pid = _coerce_positive_pid(pid)
    if pid is None:
        return False
    if os.name == 'nt':
        try:
            out = subprocess.run(
                ['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                capture_output=True, text=True, creationflags=CREATE_NO_WINDOW, timeout=5,
            )
            return str(pid) in (out.stdout or "")
        except Exception:
            return True  # 无法确认时保守认为存活
    else:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False


# 退出清理时无法及时停止的 QThread 在此“寄存”，避免随父窗口销毁而在运行中被析构
_orphan_threads = []


def detach_thread_until_finished(thread):
    """退出清理无法在超时内停止某 QThread 时调用：脱离其 Qt 父对象并保持一个
    模块级强引用，直到线程自然结束才释放。这样父窗口销毁不会连带销毁仍在运行的
    线程（否则触发 "QThread: Destroyed while thread is still running" 崩溃）。

    适用于持有阻塞子进程、无法协作式取消的 worker（如系统状态检测）。"""
    if thread is None:
        return
    try:
        thread.setParent(None)
    except Exception:
        pass
    if thread in _orphan_threads:
        return  # 已寄存，避免重复连接 finished
    _orphan_threads.append(thread)

    def _release():
        try:
            _orphan_threads.remove(thread)
        except ValueError:
            pass
    try:
        thread.finished.connect(_release)
    except Exception:
        pass


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


def stream_subprocess(
    args: List[str],
    cwd: str | None = None,
    timeout: float | None = None,
    merge_stderr: bool = True,
    line_callback: Optional[Callable[[str], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Tuple[int, List[str]]:
    """Run subprocess, return (returncode, stdout_lines).

    merge_stderr=True (default): stdout+stderr interleaved into one list.
    merge_stderr=False: stderr consumed by daemon thread to prevent deadlock.
    line_callback: if provided, called synchronously for each line as it is
                   read, enabling real-time UI updates.
    should_cancel: if provided, a daemon thread polls it every 0.2s and
                   terminates the child process when it returns True — this
                   lets a caller (e.g. a QThread worker) actually cancel an
                   otherwise-blocking pip/git call instead of merely setting a
                   flag the blocking read never observes.
    Applies CREATE_NO_WINDOW on Windows, utf-8 with replace on decode errors.
    """
    stderr = subprocess.STDOUT if merge_stderr else subprocess.PIPE
    proc = subprocess.Popen(
        args, cwd=cwd, stdout=subprocess.PIPE, stderr=stderr,
        text=True, encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    # 当 merge_stderr=False 时，用守护线程消费 stderr 防止管道堵塞死锁
    if not merge_stderr and proc.stderr:
        def _drain_stderr():
            try:
                for _ in proc.stderr:
                    pass
            except (OSError, ValueError):
                pass
        threading.Thread(target=_drain_stderr, daemon=True).start()

    # 取消看门狗：轮询 should_cancel()，为真时终止子进程，使阻塞的读循环结束
    cancel_stop = None
    if should_cancel is not None:
        cancel_stop = threading.Event()

        def _watch_cancel():
            while not cancel_stop.wait(0.2):
                if should_cancel():
                    try:
                        proc.terminate()
                        try:
                            proc.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    except (ProcessLookupError, OSError):
                        pass
                    return
        threading.Thread(target=_watch_cancel, daemon=True).start()

    lines: List[str] = []
    try:
        for line in proc.stdout:
            stripped = line.rstrip("\n")
            lines.append(stripped)
            if line_callback:
                line_callback(stripped)
        proc.wait(timeout=timeout)
        return proc.returncode, lines
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except (ProcessLookupError, OSError):
            pass
        proc.wait()
        return -1, lines
    finally:
        if cancel_stop is not None:
            cancel_stop.set()