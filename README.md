# Kira Environment Manager

基于 [PyQt5](https://www.riverbankcomputing.com/software/pyqt/) + [qfluentwidgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) 的 Fluent Design 桌面应用，一站式下载、配置、运行和管理多个 [KiraAI](https://github.com/xxynet/KiraAI) 实例。

## 截图

> TODO: 添加应用截图

## 功能

### 首页仪表盘
四张状态卡片实时展示当前环境的 Python 版本、KiraAI 项目状态、Git 可用性以及运行中的实例数量。一键快捷跳转到各功能页面。

### 环境配置
- 自动检测系统中可用的 Python 版本，未检测到则提供下载引导
- 管理 7 个 pip 镜像源（清华、阿里云、中科大、华为、腾讯、豆瓣、PyPI），支持一键测速切换
- 创建虚拟环境和安装项目依赖

### 项目管理
- 从 GitHub 克隆 KiraAI 项目，支持 6 条代理通道自动测速选择最快线路（gh-proxy、ghproxy、gitclone.com、kkgithub、cnb.cool）
- 添加已有的本地 KiraAI 项目
- 查看版本信息和拉取更新

### 启动管理
- 多实例卡片式管理，每张卡片独立展示端口、项目路径、数据目录、依赖状态
- 支持同时启动多个 KiraAI 进程，各实例运行在不同端口和独立数据目录
- 实时控制台输出，支持按实例过滤日志
- 端口撞探检测：启动时自动扫描已配置端口，发现残留进程提供一键清理
- 实例重命名、配置 webui.json（端口/认证）

### 浏览器
一键在系统浏览器中打开 KiraAI WebUI，自动获取每实例的对应端口。

### 日志
- 日志文件自动轮转（5MB/文件，保留 7 个备份）
- 界面内实时查看，支持手动刷新和自动跟随滚动
- 一键打开日志目录

## 快速开始

### 环境要求

- Python 3.10+
- Git（用于克隆 KiraAI 项目）
- Windows / Linux / macOS

### 安装与运行

```bash
# 1. 安装依赖
pip install PyQt5 qfluentwidgets

# 2. 克隆本仓库
git clone https://github.com/<your-username>/kira-manager.git
cd kira-manager

# 3. 运行
python -m kira_manager.main
```

或通过 pip 安装：

```bash
pip install -e .
kira-manager
```

### 使用流程

1. **环境配置** — 确认 Python 可用 → 选择 pip 镜像源（或自动测速）→ 创建虚拟环境
2. **项目管理** — 点击「下载 KiraAI」从 GitHub 克隆（自动选择最快代理通道），或「添加已有」选择本地项目
3. **安装依赖** — 在项目目录下自动创建 venv 并安装 `requirements.txt` 中声明的全部依赖
4. **启动实例** — 在卡片上点击「启动」，进程在后台运行，控制台实时输出日志
5. **查看 WebUI** — 点击「查看」在系统浏览器中打开对应端口的 WebUI
6. **多实例管理** — 可以添加多个实例，分配不同端口和数据目录，互不干扰

## 技术细节

| 特性 | 说明 |
|---|---|
| **线程模型** | Git 克隆、pip 安装、端口测速、进程监控均在 `QThread` 中异步执行，不阻塞 UI |
| **进程管理** | 使用 `subprocess.Popen` 启停 KiraAI 进程，3 秒优雅关闭 + 2 秒强制终止；Windows 下通过 `taskkill /T` 终止整个进程树（适配 KiraAI 的 supervisor/child 架构） |
| **端口检测** | 每 2 秒通过 socket 连接检测实例端口状态，实时更新卡片运行/停止 UI |
| **配置持久化** | 线程安全的 JSON 配置，mtime 缓存避免重复 I/O，写入采用先写临时文件再 `os.replace` 的原子操作 |
| **日志系统** | 统一日志池捕获全局异常、Qt 内部消息、stdout/stderr，全部写入轮转日志文件 |
| **性能优化** | 关闭 Mica/Acrylic 毛玻璃效果，避免 DWM 合成和 gaussianBlur 带来的额外 CPU/GPU 开销 |
| **高 DPI** | Qt 5.14 以下自动启用 `AA_EnableHighDpiScaling`，所有版本使用 `PassThrough` 缩放策略 |

## 项目结构

```
kira-manager/
├── pyproject.toml
├── requirements.txt
├── run.py
├── README.md
└── kira_manager/
    ├── main.py                  # 程序入口
    ├── __init__.py              # 包声明 + 版本号
    ├── resources/
    │   └── icon.png             # 应用图标
    ├── common/
    │   ├── config.py            # 线程安全 JSON 配置（mtime 缓存）
    │   └── constants.py         # 项目级常量
    ├── utils/
    │   ├── instance_manager.py  # 多实例管理器（KiraInstance + InstanceManager）
    │   ├── process_manager.py   # 子进程生命周期管理
    │   ├── python_env.py        # Python/venv 检测、创建、依赖安装
    │   ├── project.py           # Git 克隆/拉取、版本检测、项目校验
    │   ├── network.py           # GitHub 代理加速通道管理与测速
    │   ├── pip_mirrors.py       # pip 镜像源管理与测速
    │   ├── logger.py            # 统一日志（轮转文件 + Qt 消息 + 全局异常）
    │   └── helpers.py           # UI 辅助（控制台滚动、端口检测、色彩常量）
    ├── view/
    │   ├── main_window.py       # FluentWindow 主窗口（6 页侧边导航）
    │   ├── home_page.py         # 首页仪表盘
    │   ├── env_page.py          # 环境配置页
    │   ├── project_page.py      # 项目管理页
    │   ├── launch_page.py       # 启动管理页（多实例卡片 + 控制台）
    │   ├── config_page.py       # webui.json 配置编辑弹窗
    │   ├── browser_page.py      # 浏览器页
    │   └── log_page.py          # 日志查看页
    └── logs/                    # 运行日志目录（自动生成）
```

## 上游项目

- [**KiraAI**](https://github.com/xxynet/KiraAI) — 多平台 AI 数字生命系统，本管理器所管理的目标项目
- [**PyQt-Fluent-Widgets**](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) — Fluent Design 风格的 PyQt5 组件库，本项目的 UI 框架

## 许可证

本项目继承 KiraAI 的 [AGPL-3.0](https://www.gnu.org/licenses/agpl-3.0.html) 许可证。

qfluentwidgets 非商业用途使用 GPLv3，商业用途需向作者获取授权。
