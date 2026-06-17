"""项目级常量 —— 集中管理所有硬编码数值"""

import os
import sys
from pathlib import Path


def get_app_data_dir():
    """返回应用程序数据目录（配置、日志等持久化文件存放位置）

    冻结模式：使用平台标准用户数据目录（可写）
    开发模式：使用代码所在目录
    """
    if getattr(sys, 'frozen', False):
        if os.name == 'nt':
            base = os.environ.get('APPDATA', os.path.expanduser('~'))
            return Path(base) / "KiraEnvManager"
        elif sys.platform == 'darwin':
            return Path(os.path.expanduser('~')) / "Library" / "Application Support" / "KiraEnvManager"
        else:
            return Path(os.environ.get('XDG_CONFIG_HOME', os.path.expanduser('~/.config'))) / "kira-env-manager"
    else:
        return Path(__file__).parent.parent


# KiraAI 默认端口
DEFAULT_PORT = 5267

# 主窗口尺寸
WINDOW_WIDTH = 1200
WINDOW_HEIGHT = 780

# 页面统一边距 (left, top, right, bottom)
PAGE_MARGINS = (36, 24, 36, 24)

# 按钮固定高度
BUTTON_HEIGHT_SMALL = 28
BUTTON_HEIGHT_MEDIUM = 30

# 日志刷新间隔 (ms)
LOG_REFRESH_INTERVAL = 2000

# 控制台最大显示行数
MAX_DISPLAY_LINES = 500

# 端口检测超时 (s)
PORT_CHECK_TIMEOUT = 0.3

# 定时端口检测间隔 (ms)
PORT_CHECK_INTERVAL = 2000

# 进程优雅关闭超时 (s)
GRACEFUL_STOP_TIMEOUT = 3

# 线程等待超时 (ms)
THREAD_WAIT_TIMEOUT = 5000


