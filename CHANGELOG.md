# Changelog

## v1.0.0 (2026-06-18)

### 🐛 Bug 修复

**跨平台与编码**

5. **非 Windows 上 subprocess 静默失效**：`creationflags=0x08000000` 无条件传入所有 `subprocess` 调用，在 macOS/Linux 上直接抛 `ValueError` 被外层 except 吞掉，导致 Python 检测、venv 创建、pip 安装、git clone/pull 全部静默返回失败。已改为平台感知常量 `CREATE_NO_WINDOW`（9 处统一替换）。
6. **非 UTF-8 编码 requirements.txt 导致崩溃**：`req_file.read_text(encoding="utf-8")` 在 try 块外部，中文 Windows GBK 编码文件抛出 `UnicodeDecodeError` 未被捕获，UI 线程直接崩溃。已加 `errors="replace"` 并移入 try 块，检测到替换字符时记录警告日志。

**进程生命周期**

7. **托盘"退出"绕过确认 → 残留进程**：`_quit_app` 调用 `close()` 后无条件 `quit()`，closeEvent 中的确认对话框和实例停止循环被跳过。改为 `closed_by_tray` 信号机制 — 仅 closeEvent 真正接受关闭时才触发 quit。
8. **端口子串匹配误杀无关进程**：`_get_pid_by_port` 用 `f":{port}" in line` 子串匹配，查端口 5267 时会命中 52670~52679，随后 `taskkill /F` 杀死无关进程。已删除该函数，改为直接查询 ProcessManager 持有的 Popen PID。
9. **修改运行中实例端口 → 实例从 UI 永久不可停止**：改端口时直接修改 `instance.cfg["port"]`，但活着的进程仍绑在旧端口，此后 `is_running()` 探测新端口显示"未运行"，卡片/浏览器 URL 失效。运行中改端口现在被拦截并提示"请先停止"。
10. **重启过渡窗口内 `stop()` 成空操作**：`_restart_process` 先将 `self._worker = None` 再挂钩 `_start_new`，此时 stop() 因 `if not self._worker: return` 直接返回，之后 `_start_new` 照常启动被用户以为已取消的进程。已加 `_restarting` 标志 + `QMutex` 保护。
11. **instance_manager.remove() 泄漏 worker QThread**：`_ProcessWorker` 创建时未设 Qt 父对象，remove 仅 `inst.deleteLater()`，QThread 及其管道句柄永不释放。已加 `deleteLater()`。

**UI 线程与线程安全**

12. **多处同步 subprocess 冻结 UI**：`_add_existing`、`_on_start` 中同步调用 `check_dependencies_installed`（内部 pip list，超时 15s）；`home_page` 的 `refresh_status` 中同步调用 `detect_python()` / `check_git_installed()`。均已改为 `QThread` worker 异步执行。
13. **`QThread.terminate()` 遗留子进程**：对正在跑 pip/git 的 QThread 调 `terminate()` 强杀线程，但派生的子进程不会被杀（文件锁残留、venv 写一半）。已改为协作式取消：设 `_cancelled` 标志 + `requestInterruption()` + `quit()` + `wait(3000)`，且 `terminate()` 超时后自动 fallback 到 `kill()`。
14. **共享 `self._worker` 槽位 → 控件永久禁用**：env_page 的测速/建 venv/装依赖共用一个 `self._worker`，启动其一会 `terminate()` 掉另一个并覆盖引用，被 terminate 的 worker 的 `finished` 永不触发 → 对应卡片永久卡在禁用态。已拆为三个独立 worker 引用（`_speedtest_worker`、`_venv_worker`、`_install_worker`），UI 状态直接管理而非依赖信号顺序。
15. **清空日志后页面不再显示日志**：`_clear_log` 把文件截断为 0、重置 `_last_size`，但未重置 `_startup_offset`，下次 seek 越过 EOF → `readlines()` 返回空 → 一直显示"暂无日志"。`RotatingFileHandler` 轮转后同理。已同步重置偏移量并加 EOF 守卫。
16. **两套"运行中"语义冲突**：`ProcessManager._running` 布尔标志 vs `InstanceManager` 的端口探测，一个启动后端口尚未 bind 的进程会被端口探测判为"未运行" → 退出时停止循环跳过 → 遗留进程。已删除标志位，统一以 `worker.isRunning()` 为唯一可信源。
17. **自定义启动参数按空格裸切**：`custom.split()` 把带引号的路径切碎（`--data-dir "C:/My Path"` → `['"C:/My', 'Path"']`）。已改为 `shlex.split()`。
18. **测速将挂掉的源选成最快**：`requests.head()` 不检查 HTTP 状态码，快速返回 403/404 的代理被选为最优源，随后真正 clone/install 失败。已加 2xx/3xx 状态检查，2xx 和重定向才视为可达。
19. **选择字体可能崩溃**：`QFontDatabase.applicationFontFamilies(font_id)[0]` 在 families 为空时抛 `IndexError`。已加判空守卫。

**已有修复（本次版本之前）**

1. **安装包增加可选安装路径**：新增 `[Code]` 段自定义目录选择页，用户可自由输入或浏览选择安装目录。
2. **"运行 x/x" 计数错误**：`running_count()` 改用 `ProcessManager` 状态判断，消除端口绑定延迟导致的漏计。
3. **全部启动/停止时 UI 卡死**：移除 `ProcessManager.stop()` 中的 `wait(500)` 阻塞调用和批量操作中的同步端口探测。
4. **控制台中文日志乱码**：子进程环境注入 `PYTHONIOENCODING=utf-8` / `PYTHONUTF8=1`，解决中文 Windows GBK 编码与 UTF-8 解码不匹配问题。

### 🔧 优化

- **提取 `stream_subprocess` 工具函数**：统一 `python_env.py`、`project.py` 中 4 处手写的 subprocess Popen+线程+流式读取样板，自动应用 `CREATE_NO_WINDOW` 和 UTF-8 replace 容错。
- **提取 `_test_url_speed` 去重测速逻辑**：`network.py` 和 `pip_mirrors.py` 各有一套 HEAD 计时+排序，合并为单一函数。
- **提取 `_parse_requirements` 去重依赖解析**：`_DepsCheckWorker` 内联重写了 `check_dependencies_installed` 的解析逻辑，现共用同一函数。
- **`_validate_env` 返回类型统一**：从 `bool` | `str` 混用改为 `Tuple[bool, str]`。
- **`_atomic_write` 改用 `NamedTemporaryFile`**：替换固定 `.tmp` 文件名，并发写更安全。
- **`InstanceCard` 构造时强制应用停止态样式**：修复 `_update_status(False)` 因状态未变化提前 return 导致构造时样式未应用的问题。

### 🗑️ 清理

- 删除死代码 `utils/system_tray.py`（全项目未被 import，实际托盘为 `tray_manager.py`）。
- 删除未使用常量 `MAX_INSTANCES`。
- 删除死方法 `_get_pid_by_port`、`_kill_process_by_pid`、`_check_port_status`。
- 删除 `import threading`（`project.py` 和 `python_env.py` 的 Popen+线程已被 `stream_subprocess` 替代）。

## v0.8.0rc (2026-06-15)

### ✨ 新功能

- **系统托盘（System Tray）**：主窗口最小化时自动缩至系统托盘，支持右键菜单快捷启停实例、打开 WebUI，双击托盘图标恢复窗口。

### 🐛 Bug 修复

1. **现有实例依赖检测卡死**  
   首次添加已有 KiraAI 实例（非本程序下载）时，即使实例依赖完整，依赖检查仍会卡死主程序。  
   → 新增 `DepCheckWorker`（`QThread`）将依赖检查移至后台，添加异常保护和超时兜底，并过滤 ANSI 转义码避免日志显示异常。

2. **现有实例端口不同步**  
   首次添加已有实例时卡片端口显示为默认顺序（5267、5268…），而非实例实际配置的端口，导致快速跳转 WebUI 地址错误。  
   → 添加时自动读取实例 `webui.json` 中的端口配置，若无配置文件则 fallback 到默认端口。

3. **第二个实例状态管理异常**  
   添加第二个及之后的实例后，不退出程序就无法正确显示为已启动状态，也无法正确停止。  
   → 根因为端口未正确同步导致状态匹配失败，修复端口同步后一并解决。

### 🔧 优化

- 依赖状态检查增加后台刷新机制，`env_page` 完成依赖安装后自动通知 `launch_page` 刷新所有实例卡片的依赖状态，不再需要完全退出程序重开。
- 日志页面过滤 ANSI 转义码，显示更清爽。
- 新增 `InstanceState` 枚举和 `state_color()` 辅助函数，统一实例状态管理。

### 📦 构建

- 迁移至 PyInstaller `--onedir` 模式 + Inno Setup 安装包打包。
- 安装包集成卸载时删除用户数据选项（可选）。
- 应用图标（app.ico）、qfluentwidgets 字体资源随包分发。
