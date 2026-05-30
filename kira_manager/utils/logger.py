"""统一日志池 — 捕获所有日志并写入文件

功能：
- 文件日志（按大小轮转，保留 7 天）
- 捕获 Python 未处理异常
- 捕获 Qt 消息（qDebug/qWarning/qCritical/qFatal）
- 捕获 stdout/stderr
- 所有 UI 错误统一通过此模块记录

用法：
    from kira_manager.utils.logger import logger, setup_logging
    setup_logging()        # 在 main() 开头调用一次
    logger.info("...")
    logger.exception("...")  # 自动附带 traceback
"""

import logging
import logging.handlers
import os
import sys
import threading
import traceback
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_FILE = LOG_DIR / "kira_manager.log"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
BACKUP_COUNT = 7              # keep 7 rotated files

logger = logging.getLogger("kira_manager")
logger.setLevel(logging.DEBUG)

_initialized = False
_log_path = None
_init_lock = threading.Lock()
_startup_offset = 0  # 启动时的文件偏移量，用于只显示本次启动后的日志


def get_startup_offset():
    """获取本次启动时的文件偏移量"""
    return _startup_offset


def _format_exception_only(exc_type, exc_value):
    """仅格式化异常类型和值，不含 traceback"""
    if exc_value is None:
        return str(exc_type.__name__) if exc_type else "Unknown"
    return f"{exc_type.__name__}: {exc_value}"


def setup_logging(log_dir=None):
    """初始化日志系统 — 在 QApplication 创建前或刚创建后调用"""
    global _initialized, _log_path, _startup_offset
    with _init_lock:
        if _initialized:
            return

        d = Path(log_dir) if log_dir else LOG_DIR
        d.mkdir(parents=True, exist_ok=True)
        log_path = d / "kira_manager.log"

        # 记录启动前的文件大小作为偏移量（只显示本次启动后的日志）
        try:
            if log_path.exists():
                _startup_offset = log_path.stat().st_size
            else:
                _startup_offset = 0
        except OSError:
            _startup_offset = 0

        # 文件 handler — 按大小轮转
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=MAX_BYTES,
            backupCount=BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)-8s %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

        # 控制台 handler — 仅 WARNING+
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(logging.WARNING)
        console_handler.setFormatter(logging.Formatter(
            "[%(levelname)s] %(message)s"
        ))

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        # 挂载 Qt 消息捕获（如果 Qt 已加载）
        _install_qt_handler()

        # 挂载全局异常钩子
        _install_excepthook()

        # 重定向 stdout/stderr
        _install_stdio_redirect()

        _log_path = str(log_path)

        logger.info("=" * 50)
        logger.info(f"Kira Environment Manager 启动 — {datetime.now().isoformat()}")
        logger.info(f"日志文件: {log_path}")

        _initialized = True


def _install_qt_handler():
    """将 Qt 消息重定向到 Python logging"""
    try:
        from PyQt5.QtCore import qInstallMessageHandler, QtMsgType

        _qt_type_map = {
            QtMsgType.QtDebugMsg: logging.DEBUG,
            QtMsgType.QtInfoMsg: logging.INFO,
            QtMsgType.QtWarningMsg: logging.WARNING,
            QtMsgType.QtCriticalMsg: logging.CRITICAL,
            QtMsgType.QtFatalMsg: logging.CRITICAL,
        }

        # 过滤掉前端 JavaScript 的无用错误
        _JS_FILTERS = [
            "SyntaxError: Invalid flags supplied to RegExp",
            "n.at is not a function",
            "markedjs/marked",
            "Please report this to https://github.com/markedjs/marked",
        ]

        def qt_message_handler(msg_type, context, message):
            # 过滤前端 JS 错误
            if any(f in message for f in _JS_FILTERS):
                return

            level = _qt_type_map.get(msg_type, logging.DEBUG)
            file = context.file or ""
            line = context.line or 0
            func = context.function or ""
            detail = f"[Qt] {message}"
            if file:
                detail += f"  ({os.path.basename(file)}:{line}"
                if func:
                    detail += f" {func}"
                detail += ")"
            logger.log(level, detail)

        qInstallMessageHandler(qt_message_handler)
        logger.debug("Qt 消息处理器已安装")
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"安装 Qt 消息处理器失败: {e}")


def _install_excepthook():
    """捕获所有未处理的 Python 异常"""
    _original_hook = sys.excepthook

    def global_excepthook(exc_type, exc_value, exc_tb):
        tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.critical(f"未处理异常:\n{tb_text}")

        try:
            from PyQt5.QtWidgets import QApplication
            from PyQt5.QtCore import QThread
            app = QApplication.instance()
            in_main_thread = app and QThread.currentThread() is app.thread()
        except ImportError:
            in_main_thread = False

        if in_main_thread:
            try:
                from PyQt5.QtWidgets import QApplication, QMessageBox
                from qfluentwidgets import InfoBar, InfoBarPosition
                app = QApplication.instance()
                if app:
                    active = app.activeWindow()
                    if active:
                        try:
                            InfoBar.error(
                                "运行错误",
                                str(exc_value)[:200] if exc_value else str(exc_type.__name__),
                                duration=8000,
                                position=InfoBarPosition.TOP_RIGHT,
                                parent=active,
                            )
                            if _original_hook is not sys.__excepthook__:
                                _original_hook(exc_type, exc_value, exc_tb)
                            return
                        except Exception:
                            pass

                    QMessageBox.critical(
                        None, "运行错误",
                        f"{_format_exception_only(exc_type, exc_value)}\n\n详情已写入日志。\n程序将继续运行。",
                    )
            except Exception:
                pass

        if _original_hook is not sys.__excepthook__:
            _original_hook(exc_type, exc_value, exc_tb)

    sys.excepthook = global_excepthook
    logger.debug("全局异常钩子已安装")

    if hasattr(threading, 'excepthook'):
        _original_thread_hook = getattr(threading, 'excepthook', None)

        def thread_excepthook(args):
            tb_text = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_tb))
            logger.critical(f"线程未处理异常:\n{tb_text}")
            if _original_thread_hook:
                _original_thread_hook(args)

        threading.excepthook = thread_excepthook


class _StreamToLogger:
    """将 stdout/stderr 内容转发到 logger"""

    def __init__(self, logger_instance, level):
        self._logger = logger_instance
        self._level = level
        self._lock = threading.Lock()
        self.encoding = 'utf-8'

    def write(self, text):
        if not text or not text.strip():
            return
        with self._lock:
            for line in text.rstrip().splitlines():
                stripped = line.strip()
                if stripped:
                    self._logger.log(self._level, stripped)

    def flush(self):
        pass

    def isatty(self):
        return False

    def fileno(self):
        raise OSError("stream does not have a file descriptor")


def _install_stdio_redirect():
    """将 stdout/stderr 重定向到日志"""
    sys.stdout = _StreamToLogger(logger, logging.INFO)
    sys.stderr = _StreamToLogger(logger, logging.ERROR)
    logger.debug("stdout/stderr 已重定向到日志")


def get_log_path():
    """返回当前日志文件路径"""
    if _log_path:
        return _log_path
    d = LOG_DIR
    if d.exists():
        files = sorted(d.glob("kira_manager.log*"), key=os.path.getmtime, reverse=True)
        if files:
            return str(files[0])
    return str(LOG_DIR / "kira_manager.log")


# ---- UI 通知函数（自动记录日志）----

def notify_info(title, message, parent=None, duration=3000):
    """显示 InfoBar 信息通知并记录到日志"""
    logger.info(f"[通知] {title}: {message}")
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.info(title, message, duration=duration,
                    position=InfoBarPosition.TOP_RIGHT, parent=parent)
    except Exception:
        pass


def notify_success(title, message, parent=None, duration=3000):
    """显示 InfoBar 成功通知并记录到日志"""
    logger.info(f"[成功] {title}: {message}")
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.success(title, message, duration=duration,
                       position=InfoBarPosition.TOP_RIGHT, parent=parent)
    except Exception:
        pass


def notify_warning(title, message, parent=None, duration=3000):
    """显示 InfoBar 警告通知并记录到日志"""
    logger.warning(f"[警告] {title}: {message}")
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.warning(title, message, duration=duration,
                       position=InfoBarPosition.TOP_RIGHT, parent=parent)
    except Exception:
        pass


def notify_error(title, message, parent=None, duration=5000):
    """显示 InfoBar 错误通知并记录到日志"""
    logger.error(f"[错误] {title}: {message}")
    try:
        from qfluentwidgets import InfoBar, InfoBarPosition
        InfoBar.error(title, message, duration=duration,
                     position=InfoBarPosition.TOP_RIGHT, parent=parent)
    except Exception:
        pass


def notify_critical(title, message, parent=None):
    """显示 QMessageBox 严重错误对话框并记录到日志"""
    logger.critical(f"[严重错误] {title}: {message}")
    try:
        from PyQt5.QtWidgets import QMessageBox
        QMessageBox.critical(parent, title, message)
    except Exception:
        pass
