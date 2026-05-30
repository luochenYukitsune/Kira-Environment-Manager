"""pip 镜像源管理 — 多源列表、测速、智能选择"""

import urllib.request
import time


# 常用 pip 镜像源（名称, URL, 描述）
MIRRORS = [
    ("PyPI 官方", "https://pypi.org/simple/", "官方源，海外速度快"),
    ("清华 TUNA", "https://pypi.tuna.tsinghua.edu.cn/simple/", "清华大学开源镜像站"),
    ("阿里云", "https://mirrors.aliyun.com/pypi/simple/", "阿里巴巴开源镜像站"),
    ("中科大 USTC", "https://pypi.mirrors.ustc.edu.cn/simple/", "中国科学技术大学镜像站"),
    ("华为云", "https://repo.huaweicloud.com/repository/pypi/simple/", "华为云镜像站"),
    ("腾讯云", "https://mirrors.cloud.tencent.com/pypi/simple/", "腾讯云镜像站"),
    ("豆瓣", "https://pypi.douban.com/simple/", "豆瓣 PyPI 镜像"),
]


def get_mirror_url(index):
    """根据索引获取镜像 URL，越界时返回默认"""
    if 0 <= index < len(MIRRORS):
        return MIRRORS[index][1]
    return MIRRORS[0][1]


def get_mirror_name(index):
    """根据索引获取镜像名称，越界时返回默认"""
    if 0 <= index < len(MIRRORS):
        return MIRRORS[index][0]
    return MIRRORS[0][0]


def safe_mirror_index(index):
    """确保镜像索引在有效范围内"""
    return min(max(0, index), len(MIRRORS) - 1)


def test_single_mirror(url, timeout=5):
    """测试单个镜像源的响应时间

    Returns:
        latency_ms 或 None（不可达）
    """
    try:
        start = time.time()
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Kira-Manager/1.0")
        with urllib.request.urlopen(req, timeout=timeout):
            pass
        elapsed = (time.time() - start) * 1000
        return round(elapsed, 1)
    except Exception:
        return None


def test_all_mirrors(callback=None):
    """测试所有镜像源的速度

    Args:
        callback: 可选回调 (name, url, latency_ms | None)

    Returns:
        [(name, url, latency_ms | None), ...] 按延迟排序
    """
    results = []
    for name, url, desc in MIRRORS:
        latency = test_single_mirror(url)
        results.append((name, url, latency))
        if callback:
            callback(name, url, latency)

    # 按延迟排序（None 排最后）
    results.sort(key=lambda x: x[2] if x[2] is not None else float("inf"))
    return results


def find_fastest_mirror(timeout=5):
    """找到最快的可用镜像源

    Returns:
        (index, name, url, latency_ms) 或 (0, MIRRORS[0]...) 全不可达时
    """
    results = test_all_mirrors()
    if results and results[0][2] is not None:
        for i, (name, url, _) in enumerate(MIRRORS):
            if name == results[0][0] and url == results[0][1]:
                return (i, results[0][0], results[0][1], results[0][2])
        return (0, results[0][0], results[0][1], results[0][2])
    return (0, "PyPI 官方", "https://pypi.org/simple/", None)
