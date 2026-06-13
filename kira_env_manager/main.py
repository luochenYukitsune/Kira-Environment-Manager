"""Kira Environment Manager 入口"""

import sys
import os


# 确保父目录在 sys.path 中，以支持 python kira_env_manager/main.py 或 python -m kira_env_manager.main
# 冻结模式下 PyInstaller 已处理路径，无需额外操作
if not getattr(sys, 'frozen', False):
    _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _parent not in sys.path:
        sys.path.insert(0, _parent)

from PyQt5.QtCore import Qt, QT_VERSION
from PyQt5.QtGui import QFontDatabase, QFont, QSurfaceFormat
from PyQt5.QtWidgets import QApplication, QMessageBox

from qfluentwidgets import setTheme, Theme

from kira_env_manager.utils.logger import setup_logging, logger, get_log_path
from kira_env_manager.view.main_window import MainWindow


def _init_surface_format():
    """配置 OpenGL 硬件加速渲染后端 —— 必须在 QApplication 之前调用"""
    fmt = QSurfaceFormat()
    fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
    fmt.setSwapInterval(1)  # vsync
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    QSurfaceFormat.setDefaultFormat(fmt)


def _resolve_font_path():
    """解析最终字体路径：优先使用用户配置，其次内置默认"""
    from pathlib import Path

    # 1) 尝试从配置文件读取自定义字体路径
    try:
        from kira_env_manager.common.config import get as cfg_get
        cfg_path = cfg_get("font_path")
        if cfg_path:
            p = Path(cfg_path)
            if p.exists():
                return p
            logger.warning(f"配置的字体路径不存在: {cfg_path}，回退内置字体")
    except Exception:
        pass

    # 2) 回退内置字体目录
    if getattr(sys, 'frozen', False):
        font_dir = Path(sys._MEIPASS) / "kira_env_manager" / "fonts"
    else:
        font_dir = Path(__file__).parent / "fonts"

    # 尝试 HarmonyOS Sans（首选），再试苹方字体
    for name in ("HarmonyOS_Sans_Regular.ttf", "苹方字体.ttf"):
        p = font_dir / name
        if p.exists():
            return p

    return font_dir / "苹方字体.ttf"  # 不管存不存在，caller 处理


def _init_global_font(app):
    """加载自定义/内置字体并设为 QApplication 默认字体"""
    from pathlib import Path

    try:
        font_path = _resolve_font_path()
        if not font_path.exists():
            logger.warning(f"字体文件不存在: {font_path}")
            return

        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id < 0:
            logger.warning(f"字体注册失败: {font_path}")
            return

        family = QFontDatabase.applicationFontFamilies(font_id)[0]
        logger.info(f"已加载字体: {family} ({font_path.name})")

        app.setFont(QFont(family))

        # 同步到 qfluentwidgets 字体系统
        from qfluentwidgets.common.font import setFontFamilies, fontFamilies
        setFontFamilies([family] + fontFamilies())
    except Exception as e:
        logger.warning(f"字体初始化失败: {e}")


def main():
    # 渲染后端 —— 必须最先配置，锁定后不可更改
    _init_surface_format()

    # 高 DPI 支持
    # Qt 5.14+ 默认启用 AA_EnableHighDpiScaling 和 AA_UseHighDpiPixmaps，
    # 这两个属性在 Qt 6 中已废弃，此处仅在 Qt 5.14 以下版本设置
    if QT_VERSION < 0x050E00:  # Qt 5.14.0
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    # 统一日志池 —— 捕获所有异常、Qt 消息、stdout/stderr
    setup_logging()

    # 注册自定义字体并设为全局默认
    _init_global_font(app)

    setTheme(Theme.AUTO)

    try:
        window = MainWindow()
        window.show()
        logger.info("主窗口已显示")
    except Exception as e:
        logger.exception("Kira Environment Manager 启动失败")
        QMessageBox.critical(
            None, "Kira Environment Manager 启动出错",
            f"{type(e).__name__}: {e}\n\n日志文件: {get_log_path()}"
        )
        sys.exit(1)

    exit_code = app.exec_()
    logger.info(f"退出 (code={exit_code})")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
