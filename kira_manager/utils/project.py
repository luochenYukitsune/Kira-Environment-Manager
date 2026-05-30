"""KiraAI 项目管理工具"""

import os
import re
import shutil
import subprocess
from pathlib import Path


KIRA_GITHUB_URL = "https://github.com/xxynet/KiraAI"


def check_kira_version(project_path):
    """检测本地 KiraAI 项目版本

    Returns:
        version_str 或 None
    """
    try:
        p = Path(project_path)
        config_file = p / "core" / "config" / "default.py"
        if not config_file.exists():
            return None

        content = config_file.read_text(encoding='utf-8')
        match = re.search(r'VERSION\s*=\s*["\']([^"\']+)["\']', content)
        if match:
            return match.group(1)
        return None
    except Exception:
        return None


def clone_repo(url, target_path, output_callback=None, timeout=300):
    """克隆 Git 仓库

    Args:
        url: GitHub 仓库 URL
        target_path: 目标路径
        output_callback: 输出回调
        timeout: 超时秒数，默认 5 分钟

    Returns:
        (success: bool, message: str)
    """
    import time

    try:
        target = Path(target_path)
        if target.exists():
            return False, f"目标路径已存在: {target_path}"

        if output_callback:
            output_callback(f">>> git clone {url} {target_path}\n")

        proc = subprocess.Popen(
            ["git", "clone", "--progress", url, str(target_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        start_time = time.time()
        try:
            for line in proc.stdout:
                # 检查超时
                if time.time() - start_time > timeout:
                    proc.terminate()
                    try:
                        proc.wait(5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    shutil.rmtree(target_path, ignore_errors=True)
                    return False, f"克隆超时 ({timeout}秒)"

                if output_callback:
                    output_callback(line)
        finally:
            if proc.stdout:
                proc.stdout.close()

        proc.wait()

        if proc.returncode == 0:
            version = check_kira_version(str(target_path))
            msg = f"克隆成功"
            if version:
                msg += f"，版本: {version}"
            return True, msg
        else:
            return False, f"克隆失败 (退出码: {proc.returncode})"

    except FileNotFoundError:
        return False, "未找到 git 命令，请先安装 Git (https://git-scm.com/)"
    except Exception as e:
        from kira_manager.utils.logger import logger
        logger.exception(f"Git clone 失败: {url} -> {target_path}")
        return False, f"克隆出错: {str(e)}"


def update_project(project_path, output_callback=None):
    """更新项目 (git pull)

    Returns:
        (success: bool, message: str)
    """
    try:
        p = Path(project_path)
        if not (p / ".git").exists():
            return False, "不是有效的 git 仓库"

        if output_callback:
            output_callback(f">>> cd {project_path} && git pull\n")

        proc = subprocess.Popen(
            ["git", "pull"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=str(project_path),
        )

        try:
            for line in proc.stdout:
                if output_callback:
                    output_callback(line)
        finally:
            if proc.stdout:
                proc.stdout.close()

        proc.wait()

        if proc.returncode == 0:
            version = check_kira_version(str(project_path))
            return True, f"更新成功" + (f"，版本: {version}" if version else "")
        else:
            return False, f"更新失败 (退出码: {proc.returncode})"

    except FileNotFoundError:
        return False, "未找到 git 命令"
    except Exception as e:
        from kira_manager.utils.logger import logger
        logger.exception(f"Git pull 失败: {project_path}")
        return False, f"更新出错: {str(e)}"


def check_git_installed():
    """检测 Git 是否已安装并返回版本"""
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except Exception:
        return None


def is_kira_project(path):
    """检查路径是否为有效的 KiraAI 项目"""
    if not path:
        return False
    main_py = os.path.join(path, "main.py")
    req = os.path.join(path, "requirements.txt")
    core_dir = os.path.join(path, "core")
    config_default = os.path.join(path, "core", "config", "default.py")
    return os.path.isfile(main_py) and os.path.isfile(req) and os.path.isdir(core_dir) and os.path.isfile(config_default)
