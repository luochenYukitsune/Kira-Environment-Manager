"""Python 环境检测与管理工具"""

import os
import sys
import subprocess
import threading
from pathlib import Path


def find_system_python():
    """在冻结模式下查找系统 Python 解释器"""
    if not getattr(sys, 'frozen', False):
        return sys.executable
    try:
        if os.name == 'nt':
            result = subprocess.run(
                ["py", "-3", "-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000,
            )
            if result.returncode == 0:
                path = result.stdout.strip()
                if path and os.path.isfile(path):
                    return path
            result = subprocess.run(
                ["where", "python"],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000,
            )
            if result.returncode == 0:
                candidates = [l.strip() for l in result.stdout.splitlines() if l.strip()]
                real = [p for p in candidates if "WindowsApps" not in p and os.path.isfile(p)]
                if real:
                    return real[0]
        else:
            for cmd in ["python3", "python"]:
                result = subprocess.run(
                    ["which", cmd], capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    path = result.stdout.strip()
                    if path and os.path.isfile(path):
                        return path
    except Exception:
        pass
    return None


def detect_python():
    """检测系统 Python 环境"""
    path = find_system_python()
    if path:
        try:
            result = subprocess.run(
                [path, "--version"],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000,
            )
            if result.returncode == 0:
                version = result.stdout.strip().replace("Python ", "")
                return version, path
        except Exception:
            pass
    return "未检测到", ""


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
    """获取 venv 中的 pip.exe 路径（兼容保留，推荐使用 get_venv_pip_cmd）"""
    p = Path(venv_path)
    return str(p / "Scripts" / "pip.exe") if os.name == "nt" else str(p / "bin" / "pip")


def get_venv_pip_cmd(venv_path):
    """获取 venv 中 pip 的命令列表（使用 python -m pip 方式，兼容性更好）"""
    python_exe = get_venv_python(str(venv_path))
    return [python_exe, "-m", "pip"]


def create_venv(venv_path, python_exe=None):
    """创建虚拟环境"""
    try:
        p = Path(venv_path)
        if p.exists():
            return False, f"路径已存在: {venv_path}"
        if python_exe is None:
            python_exe = find_system_python()
        if not python_exe:
            return False, "未检测到系统 Python，请先安装 Python 3.10+"
        venv_result = subprocess.run(
            [python_exe, "-m", "venv", str(venv_path)],
            capture_output=True, text=True, timeout=120,
            creationflags=0x08000000,
        )
        if venv_result.returncode != 0:
            err = venv_result.stderr.strip() or venv_result.stdout.strip() or "未知错误"
            return False, f"venv 创建失败: {err}"
        pip_cmd = get_venv_pip_cmd(str(venv_path))
        subprocess.run(
            pip_cmd + ["install", "--upgrade", "pip"],
            capture_output=True, text=True, timeout=120,
            creationflags=0x08000000,
        )
        return True, f"虚拟环境创建成功: {venv_path}"
    except subprocess.TimeoutExpired:
        return False, "创建超时"
    except Exception as e:
        return False, f"创建失败: {str(e)}"


def _normalize_pkg_name(name):
    return name.lower().replace("_", "-").strip()


def check_dependencies_installed(venv_path, requirements_path):
    """检查 venv 中的依赖是否已安装"""
    pip_cmd = get_venv_pip_cmd(str(venv_path))
    req_file = Path(requirements_path)
    if not req_file.exists():
        return False, [], f"找不到 requirements.txt: {requirements_path}"
    required = set()
    for line in req_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        pkg = line.split("==")[0].split(">=")[0].split("~=")[0].split("<")[0].split("!=")[0].split(">")[0]
        pkg = pkg.split("[")[0].split(";")[0].split("@")[0].strip()
        if pkg:
            required.add(_normalize_pkg_name(pkg))
    try:
        result = subprocess.run(
            pip_cmd + ["list", "--format=freeze"],
            capture_output=True, text=True, timeout=15,
            encoding='utf-8', errors='replace',
            creationflags=0x08000000,
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
                         output_callback=None, timeout=600):
    """安装依赖（使用 python -m pip 调用，兼容性更好）"""
    try:
        pip_cmd = get_venv_pip_cmd(str(venv_path))
        pip_display = f"{pip_cmd[0]} -m pip"
        req = Path(requirements_path)
        if not req.exists():
            return False, f"找不到 requirements.txt: {requirements_path}"
        if output_callback:
            output_callback(f">>> {pip_display} install -r {requirements_path}\n")
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
            cmd = pip_cmd + ["install", "-r", str(requirements_path)]
            if m:
                cmd += ["-i", m]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, bufsize=1,
                                    creationflags=0x08000000)
            _stop_reader = [False]
            def _reader(process=proc):
                for line in process.stdout:
                    if _stop_reader[0]:
                        break
                    if output_callback:
                        output_callback(line)
            reader = threading.Thread(target=_reader, daemon=True)
            reader.start()
            try:
                proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                _stop_reader[0] = True
                proc.kill()
                proc.wait()
                if output_callback:
                    output_callback(f"\n>>> {m.split('/')[2] if m else 'PyPI'} 安装超时 ({timeout}秒)\n")
                continue
            finally:
                if proc.stdout:
                    try:
                        proc.stdout.close()
                    except OSError:
                        pass
                reader.join(timeout=3)
            if proc.returncode == 0:
                src_name = m.split("/")[2] if m else "PyPI"
                return True, f"依赖安装成功 ({src_name})"
        return False, "所有源均安装失败"
    except FileNotFoundError:
        return False, f"找不到 python: {pip_cmd[0] if pip_cmd else '未知'}"
    except Exception as e:
        from kira_env_manager.utils.logger import logger
        logger.exception(f"依赖安装失败: {requirements_path}")
        return False, f"安装出错: {str(e)}"