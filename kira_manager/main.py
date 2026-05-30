"""Kira Environment Manager 入口 — 使用 python -m kira_manager.main 启动"""

import sys
import os

from PyQt5.QtCore import Qt, QT_VERSION
from PyQt5.QtGui import QSurfaceFormat
from PyQt5.QtWidgets import QApplication, QMessageBox

from qfluentwidgets import setTheme, Theme

from kira_manager.utils.logger import setup_logging, logger, get_log_path
from kira_manager.view.main_window import MainWindow


def _init_surface_format():
    """配置 OpenGL 硬件加速渲染后端 —— 必须在 QApplication 之前调用"""
    fmt = QSurfaceFormat()
    fmt.setSwapBehavior(QSurfaceFormat.DoubleBuffer)
    fmt.setSwapInterval(1)
    fmt.setRenderableType(QSurfaceFormat.OpenGL)
    QSurfaceFormat.setDefaultFormat(fmt)


def main():
    _init_surface_format()

    # 高 DPI 支持
    if QT_VERSION < 0x050E00:
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    setup_logging()

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
