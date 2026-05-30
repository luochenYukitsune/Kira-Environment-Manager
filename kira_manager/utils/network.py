"""GitHub 克隆加速 — 多代理/镜像测速 + 智能选择"""

import time
import urllib.request

# GitHub 访问方案：[名称, 克隆前缀, 测试URL, 描述]
GITHUB_ROUTES = [
    ("直连", "https://github.com", "https://github.com/xxynet/KiraAI.git", "默认直连"),
    ("gh-proxy", "https://gh-proxy.com", "https://gh-proxy.com/https://github.com/xxynet/KiraAI.git", "GitHub 代理加速"),
    ("ghproxy", "https://ghproxy.com", "https://ghproxy.com/https://github.com/xxynet/KiraAI.git", "ghproxy 镜像"),
    ("gitclone.com", "https://gitclone.com", "https://gitclone.com/github.com/xxynet/KiraAI.git", "gitclone 缓存"),
    ("kkgithub", "https://kkgithub.com", "https://kkgithub.com/xxynet/KiraAI.git", "kk 镜像 (国内快)"),
    ("cnb.cool", "https://cnb.cool", "https://cnb.cool/github.com/xxynet/KiraAI.git", "CNB 国内镜像"),
]


def _normalize_repo(repo_input):
    """将用户输入的仓库地址归一化为 'owner/repo' 格式"""
    url = repo_input.strip().rstrip("/")
    # 去掉 https://github.com/ 前缀
    for prefix in ["https://github.com/", "http://github.com/", "github.com/"]:
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    # 去掉 .git 后缀
    if url.endswith(".git"):
        url = url[:-4]
    return url if "/" in url else f"xxynet/{url}"


def convert_to_clone_url(route, repo_path="xxynet/KiraAI"):
    """将路由信息转换为 git clone URL"""
    name, prefix, _, _ = route
    repo_path = _normalize_repo(repo_path)
    if name == "直连":
        return f"https://github.com/{repo_path}.git"
    elif name in ("gh-proxy", "ghproxy"):
        return f"{prefix}/https://github.com/{repo_path}.git"
    elif name == "gitclone.com":
        return f"{prefix}/github.com/{repo_path}.git"
    elif "cnb.cool" in name:
        return f"https://cnb.cool/{repo_path}.git"
    else:
        return f"{prefix}/{repo_path}.git"


def test_route(route, timeout=5):
    """测试单个 GitHub 访问方案

    Returns:
        latency_ms 或 None（不可达）
    """
    _, _, test_url, _ = route
    headers = {"User-Agent": "Kira-Manager/1.0"}
    try:
        start = time.time()
        req = urllib.request.Request(test_url, method="HEAD", headers=headers)
        with urllib.request.urlopen(req, timeout=timeout):
            pass
        return round((time.time() - start) * 1000, 1)
    except Exception:
        try:
            req = urllib.request.Request(test_url, method="GET", headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                r.read(1)
            return round((time.time() - start) * 1000, 1)
        except Exception:
            return None


def find_best_route(repo_path="xxynet/KiraAI"):
    """检测所有 GitHub 访问方案，返回最快的

    Returns:
        (clone_url, name, latency_ms)
    """
    best_url, best_name, best_latency = None, "直连", None

    for route in GITHUB_ROUTES:
        latency = test_route(route)
        if latency is not None:
            clone_url = convert_to_clone_url(route, repo_path)
            if best_latency is None or latency < best_latency:
                best_url, best_name, best_latency = clone_url, route[0], latency

    if best_url is None:
        # 全部不可达，回退直连
        best_url = f"https://github.com/{_normalize_repo(repo_path)}.git"
        best_name = "直连"

    return best_url, best_name, best_latency


def test_all_routes(callback=None):
    """测试所有方案，通过 callback 报告进度

    Returns:
        [(name, latency_ms | None), ...]
    """
    results = []
    for route in GITHUB_ROUTES:
        latency = test_route(route)
        results.append((route[0], latency))
        if callback:
            callback(route[0], latency)
    results.sort(key=lambda x: x[1] if x[1] is not None else float("inf"))
    return results
