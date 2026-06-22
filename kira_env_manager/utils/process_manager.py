"""子进程管理器 - 启动/停止/监控 KiraAI 进程"""

import subprocess
import os
import threading
from PyQt5.QtCore import QObject, QThread, pyqtSignal, QMutex, QMutexLocker, QTimer


class _ProcessWorker(QThread):
    """在子线程中运行进程并捕获输出"""
    output_line = pyqtSignal(str)
    process_finished = pyqtSignal(int)
    pid_ready = pyqtSignal(int)         # 子进程创建后上报真实 PID

    def __init__(self, cmd, cwd=None, env=None):
        super().__init__()
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self._process = None
        self._stop_requested = False

    def run(self):
        try:
            env = os.environ.copy()
            if self.env:
                env.update(self.env)

            # 强制子进程使用 UTF-8 输出，避免中文 Windows GBK 编码导致乱码
            env.setdefault("PYTHONIOENCODING", "utf-8")
            env.setdefault("PYTHONUTF8", "1")

            # Windows: CREATE_NO_WINDOW 防止弹出黑色控制台窗口
            # Linux/macOS: 不需要特殊标志
            self._process = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                errors='replace',
                bufsize=1,
                cwd=self.cwd,
                env=env,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
            )
            self.pid_ready.emit(self._process.pid)

            try:
                for line in self._process.stdout:
                    if self._stop_requested:
                        break
                    self.output_line.emit(line)
            finally:
                if self._process.stdout:
                    try:
                        self._process.stdout.close()
                    except OSError:
                        pass

            # 等待进程结束
            if self._process.poll() is None:
                self._process.wait()

            exit_code = self._process.returncode if self._process else -1
            self.process_finished.emit(exit_code)

        except Exception as e:
            from kira_env_manager.utils.logger import logger
            logger.exception(f"进程启动失败: {self.cmd}")
            self.output_line.emit(f"\n[ERROR] 启动失败: {str(e)}\n"
                                  f"(详情已写入日志: kira_env_manager/logs/)\n")
            self.process_finished.emit(-1)

    def stop(self):
        """停止进程 — 终止整个进程树（KiraAI 采用 supervisor/child 架构）"""
        self._stop_requested = True
        if not self._process or self._process.poll() is not None:
            return

        pid = self._process.pid

        def _terminate_process_tree():
            try:
                if os.name == 'nt':
                    subprocess.run(
                        ['taskkill', '/F', '/T', '/PID', str(pid)],
                        capture_output=True,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                        timeout=5,
                    )
                else:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
                        self._process.wait(timeout=2)
            except Exception:
                pass

        threading.Thread(target=_terminate_process_tree, daemon=True).start()


class ProcessManager(QObject):
    """管理 KiraAI 进程的生命周期"""

    output_received = pyqtSignal(str)
    state_changed = pyqtSignal(bool)
    finished = pyqtSignal(int)
    pid_ready = pyqtSignal(int)         # 转发子进程 PID（供持久化 / 残留检测）

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._pid = None
        self._restarting = False
        self._restarting_mutex = QMutex()
        # 重启过渡状态（由 _start_new_worker 消费）
        self._old_worker = None
        self._pending_restart = None
        self._restart_done = True

    @property
    def pid(self):
        return self._pid

    def is_running(self):
        """Single source of truth: worker is alive and not being stopped."""
        if not self._worker:
            return False
        return self._worker.isRunning()

    def start(self, cmd, cwd=None, env=None):
        """启动进程

        Args:
            cmd: 命令列表，如 ["python", "main.py"]
            cwd: 工作目录
            env: 额外环境变量 dict
        """
        if self.is_running():
            self.output_received.emit("[WARN] 进程已在运行中\n")
            return False

        if self._worker:
            if self._worker.isRunning():
                # 停止旧 worker 并安排重启。_start_new_worker 是 ProcessManager 的
                # 绑定方法（QObject 处于 GUI 线程），因此 old_worker 在工作线程发出的
                # process_finished 会以 QueuedConnection 投递到 GUI 线程——届时 run()
                # 已返回、old_worker 已结束，可安全删除并启动新 worker。
                old_worker = self._worker
                self._worker = None

                # 旧 worker 的 process_finished 此后只用于驱动重启；断开生命周期
                # 回调，避免重启过程中误发 finished/state_changed(False)，以及旧进程
                # 退出时 clear_running_pid 与新进程 record_running_pid 相互竞争。
                try:
                    old_worker.process_finished.disconnect(self._on_finished)
                except (TypeError, RuntimeError):
                    pass

                locker = QMutexLocker(self._restarting_mutex)
                self._restarting = True
                self._restart_done = False
                self._old_worker = old_worker
                self._pending_restart = (cmd, cwd, env)

                old_worker.process_finished.connect(self._start_new_worker)
                old_worker.stop()
                # 兜底：若进程无法收割导致 process_finished 永不触发，5s 后在 GUI
                # 线程强制推进，避免重启被静默丢失且 _restarting 永久卡 True。
                QTimer.singleShot(5000, self._start_new_worker)
                return True

            self._worker.deleteLater()
            self._worker = None

        self._worker = _ProcessWorker(cmd, cwd, env)
        self._worker.output_line.connect(self._on_output)
        self._worker.process_finished.connect(self._on_finished)
        self._worker.pid_ready.connect(self._on_pid_ready)
        self._worker.start()

        self.state_changed.emit(True)
        return True

    def stop(self):
        """停止进程 — 强制终止，不阻塞主线程

        taskkill /F 通常瞬间完成；进程结束后由 process_finished 信号
        异步处理状态和清理，无需在 UI 线程中 wait()。
        """
        locker = QMutexLocker(self._restarting_mutex)
        if self._restarting:
            self._restarting = False
            return  # cancel pending restart; old process already being stopped

        if not self._worker:
            return

        was_running = self.is_running()
        self.output_received.emit("\n>>> 正在停止进程...\n")
        self._worker.stop()
        # 仅在状态真正变化时才通知外部，避免无意义的卡片重建
        if was_running:
            self.state_changed.emit(False)

    def wait_for_stop(self, timeout=3000):
        if self._worker and self._worker.isRunning():
            return self._worker.wait(timeout)
        return True

    def _start_new_worker(self):
        """重启过渡的第二阶段：旧 worker 结束(或兜底超时)后在 GUI 线程启动新进程。
        幂等：process_finished 信号与兜底定时器都可触发，只执行一次。"""
        locker = QMutexLocker(self._restarting_mutex)
        if self._restart_done or not self._restarting:
            return  # 已触发过，或已被 stop() 取消
        old = self._old_worker
        if old is not None and old.isRunning():
            old.wait(1000)
            if old.isRunning():
                # 仅可能在兜底定时器(GUI 线程)触发时到此：旧进程无法收割。
                # 不删除运行中的 QThread、不抢占端口；保留引用避免崩溃，放弃本次重启。
                from kira_env_manager.utils.logger import logger
                logger.error("重启失败：旧进程未能终止，已取消自动重启")
                self.output_received.emit("\n[ERROR] 旧进程未能终止，重启已取消\n")
                self._restart_done = True
                self._restarting = False
                self.state_changed.emit(False)
                return
        self._restart_done = True
        self._restarting = False
        if old is not None:
            old.deleteLater()
            self._old_worker = None
        cmd, cwd, env = self._pending_restart
        self._pending_restart = None
        self._worker = _ProcessWorker(cmd, cwd, env)
        self._worker.output_line.connect(self._on_output)
        self._worker.process_finished.connect(self._on_finished)
        self._worker.pid_ready.connect(self._on_pid_ready)
        self._worker.start()
        self.state_changed.emit(True)

    def _on_pid_ready(self, pid):
        self._pid = pid
        self.pid_ready.emit(pid)

    def _on_output(self, line):
        self.output_received.emit(line)

    def _on_finished(self, exit_code):
        self._pid = None
        self.state_changed.emit(False)
        self.finished.emit(exit_code)
