"""管理器配置 - 记住用户的项目路径、venv、镜像、多开实例等设置

带有内存缓存层：首次读取后缓存于内存，每次 get() 仅检查文件 mtime，
文件未变更时直接返回缓存，避免重复 JSON I/O。
"""

import copy
import json
import os
import threading
from pathlib import Path

from kira_env_manager.common.constants import get_app_data_dir


DEFAULT_CONFIG = {
    "project_path": "",
    "venv_path": "",
    "python_path": "",
    "kira_repo_url": "https://github.com/xxynet/KiraAI",
    "disable_auth": False,
    "auto_scroll_console": True,
    "mirror_index": 2,  # 默认阿里云
    "auto_detect_mirror": True,  # 安装前自动测速
    "font_path": "",  # 自定义字体路径，空=使用内置默认字体
    "instances": [],  # [{name, port, data_dir, project_path, extra_args}]
    "tray_close_action": "ask",  # "ask"=每次询问 | "minimize"=缩托盘 | "exit"=直接退出
}

CONFIG_FILE = get_app_data_dir() / "manager_config.json"

_lock = threading.RLock()
_cache = None
_cache_mtime = 0


def _ensure_config_file():
    """首次运行时自动从 DEFAULT_CONFIG 生成配置文件"""
    if not CONFIG_FILE.exists():
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        except OSError:
            pass


def _read_file():
    _ensure_config_file()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg = copy.deepcopy(DEFAULT_CONFIG)
            cfg.update(data)
            return cfg
        except Exception as e:
            try:
                from kira_env_manager.utils.logger import logger
                logger.warning(f"读取配置文件失败 ({CONFIG_FILE}): {e}")
            except ImportError:
                pass
    return copy.deepcopy(DEFAULT_CONFIG)


def _get_mtime():
    try:
        return os.path.getmtime(str(CONFIG_FILE))
    except OSError:
        return 0


def load_config():
    """读取配置（强制刷新缓存）"""
    global _cache, _cache_mtime
    with _lock:
        _cache = _read_file()
        _cache_mtime = _get_mtime()
        return copy.deepcopy(_cache)


def _write_atomic(cfg):
    """仅执行原子写入（不涉及缓存更新，调用方负责在适当的锁范围内使用）"""
    tmp = CONFIG_FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
        os.replace(str(tmp), str(CONFIG_FILE))
        return True
    except Exception as e:
        try:
            if tmp.exists():
                tmp.unlink()
        except OSError:
            pass
        try:
            from kira_env_manager.utils.logger import logger
            logger.warning(f"写入配置文件失败 ({CONFIG_FILE}): {e}")
        except ImportError:
            pass
        return False


def save_config(cfg):
    """写入配置并更新缓存（外部调用入口）"""
    global _cache, _cache_mtime
    with _lock:
        old_cache = _cache
        old_mtime = _cache_mtime
        _cache = copy.deepcopy(cfg)
        if _write_atomic(cfg):
            _cache_mtime = _get_mtime()
        else:
            _cache = old_cache
            _cache_mtime = old_mtime


def get(key):
    global _cache, _cache_mtime
    with _lock:
        mtime = _get_mtime()
        if _cache is None or mtime != _cache_mtime:
            _cache = _read_file()
            _cache_mtime = mtime
        return _cache.get(key, DEFAULT_CONFIG.get(key))


def set_config(key, value):
    global _cache, _cache_mtime
    with _lock:
        mtime = _get_mtime()
        if _cache is None or mtime != _cache_mtime:
            _cache = _read_file()
            _cache_mtime = mtime
        old_value = _cache.get(key)
        _cache[key] = value
        cfg_copy = copy.deepcopy(_cache)
        if _write_atomic(cfg_copy):
            _cache_mtime = _get_mtime()
        else:
            # 写入失败，回滚内存缓存
            _cache[key] = old_value


def full():
    """返回完整配置对象（可修改后回写）—— 强制从磁盘读取，确保拿到最新数据"""
    return load_config()


def save_full(cfg):
    save_config(cfg)
