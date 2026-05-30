"""Python 环境检测与管理工具"""

import os
import sys
import subprocess
import venv
from pathlib import Path


def detect_python():
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return version, sys.executable


def get_python_download_urls():
    return [
        ("Python 官网", "https://www.python.org/downloads/"),
        ("Microsoft Store (Windows)", "https://apps.microsoft.com/search?query=python"),
        ("Python 3.12 (直接下载)", "https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe"),
        ("Python 3.11 (直接下载)", "https://www.python.org/ftp/python/3.11.11/python-3.11.11-amd64.exe"),
    ]


def is_venv(path):
    if not path:
        return False
    p = Path(path)
    if os.name == "nt":
        return (p / "Scripts" / "python.exe").exists() and (p / "Scripts" / "activate.bat").exists()
    else:
        return (p / "bin" / "python").exists() and (p / "bin" / "activate").exists()


def get_venv_python(venv_path):
    p = Path(venv_path)
    return str(p / "Scripts" / "python.exe") if os.name == "nt" else str(p / "bin" / "python")


def get_venv_pip(venv_path):
    p = Path(venv_path)
    return str(p / "Scripts" / "pip.exe") if os.name == "nt" else str(p / "bin" / "pip")


def create_venv(venv_path):
    try:
        p = Path(venv_path)
        if p.exists():
            return False, f"路径已存在: {venv_path}"
        venv.create(p, with_pip=True)
        pip = get_venv_pip(str(p))
        subprocess.run([pip, "install", "--upgrade", "pip"],
                       capture_output=True, text=True, timeout=120)
        return True, f"虚拟环境创建成功: {venv_path}"
    except subprocess.TimeoutExpired:
        return False, "创建超时"
    except Exception as e:
        return False, f"创建失败: {str(e)}"


def _normalize_pkg_name(name):
    """标准化包名：小写，连字符和下划线统一为连字符"""
    return name.lower().replace("_", "-").strip()


def check_dependencies_installed(venv_path, requirements_path):
    """检查 venv 中的依赖是否已安装

    Returns:
        (all_installed: bool, missing: list[str], message: str)
    """
    pip = get_venv_pip(str(venv_path))
    req_file = Path(requirements_path)
    if not req_file.exists():
        return False, [], f"找不到 requirements.txt: {requirements_path}"

    # 读取 requirements.txt，标准化包名
    required = set()
    for line in req_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        pkg = line.split("==")[0].split(">=")[0].split("~=")[0].split("<")[0].split("!=")[0].split(">")[0]
        pkg = pkg.split("[")[0].split(";")[0].split("@")[0].strip()
        if pkg:
            required.add(_normalize_pkg_name(pkg))

    # 获取已安装的包，标准化包名
    try:
        result = subprocess.run(
            [pip, "list", "--format=freeze"],
            capture_output=True, text=True, timeout=15,  # 15秒超时，避免长时间阻塞
            encoding='utf-8', errors='replace',
        )
        installed = set()
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("Package") or line.startswith("---") or line.startswith("WARNING"):
                continue
            if "==" in line:
                name = line.split("==")[0].strip()
                if name:
                    installed.add(_normalize_pkg_name(name))
    except subprocess.TimeoutExpired:
        return False, list(required), "检查依赖超时"
    except Exception:
        return False, list(required), "无法检查已安装的包"

    missing = sorted(p for p in required if p not in installed)
    return len(missing) == 0, missing, f"缺失 {len(missing)}/{len(required)} 个包" if missing else "全部已安装"


def install_requirements(venv_path, requirements_path,
                         mirror_url=None, fallback_mirrors=None,
                         output_callback=None):
    try:
        pip = get_venv_pip(str(venv_path))
        req = Path(requirements_path)
        if not req.exists():
            return False, f"找不到 requirements.txt: {requirements_path}"

        if output_callback:
            output_callback(f">>> {pip} install -r {requirements_path}\n")

        mirrors_to_try = []
        if mirror_url:
            mirrors_to_try.append(mirror_url)
        if fallback_mirrors:
            for m in fallback_mirrors:
                if m not in mirrors_to_try:
                    mirrors_to_try.append(m)
        if not mirrors_to_try:
            mirrors_to_try.append(None)

        for i, m in enumerate(mirrors_to_try):
            if i > 0 and output_callback:
                name = m.split("/")[2] if m else "PyPI"
                output_callback(f"\n>>> 尝试 {name} ...\n")

            cmd = [pip, "install", "-r", str(requirements_path)]
            if m:
                cmd += ["-i", m]

            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1)
            try:
                for line in proc.stdout:
                    if output_callback:
                        output_callback(line)
            finally:
                if proc.stdout:
                    proc.stdout.close()
            proc.wait()
            if proc.returncode == 0:
                src_name = m.split("/")[2] if m else "PyPI"
                return True, f"依赖安装成功 ({src_name})"

        return False, "所有源均安装失败"

    except FileNotFoundError:
        return False, f"找不到 pip: {pip}"
    except Exception as e:
        from kira_manager.utils.logger import logger
        logger.exception(f"依赖安装失败: {requirements_path}")
        return False, f"安装出错: {str(e)}"
