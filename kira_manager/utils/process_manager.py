"""子进程管理器 - 启动/停止/监控 KiraAI 进程"""

import subprocess
import os
from PyQt5.QtCore import QObject, QThread, pyqtSignal


class _ProcessWorker(QThread):
    """在子线程中运行进程并捕获输出"""
    output_line = pyqtSignal(str)
    process_finished = pyqtSignal(int)

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
            from kira_manager.utils.logger import logger
            logger.exception(f"进程启动失败: {self.cmd}")
            self.output_line.emit(f"\n[ERROR] 启动失败: {str(e)}\n"
                                  f"(详情已写入日志: kira_manager/logs/)\n")
            self.process_finished.emit(-1)

    def stop(self):
        """停止进程 — 终止整个进程树（KiraAI 采用 supervisor/child 架构）"""
        self._stop_requested = True
        if not self._process or self._process.poll() is not None:
            return

        try:
            if os.name == 'nt':
                # Windows: 使用 taskkill /T 终止进程树（supervisor 会启动子进程）
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(self._process.pid)],
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


class ProcessManager(QObject):
    """管理 KiraAI 进程的生命周期"""

    output_received = pyqtSignal(str)
    state_changed = pyqtSignal(bool)
    finished = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._running = False

    def is_running(self):
        return self._running

    def start(self, cmd, cwd=None, env=None):
        """启动进程

        Args:
            cmd: 命令列表，如 ["python", "main.py"]
            cwd: 工作目录
            env: 额外环境变量 dict
        """
        if self._running:
            self.output_received.emit("[WARN] 进程已在运行中\n")
            return False

        if self._worker:
            if self._worker.isRunning():
                self._worker.stop()
                self._worker.wait(5000)
            self._worker.deleteLater()
            self._worker = None

        self._worker = _ProcessWorker(cmd, cwd, env)
        self._worker.output_line.connect(self._on_output)
        self._worker.process_finished.connect(self._on_finished)
        self._worker.start()

        self._running = True
        self.state_changed.emit(True)
        return True

    def stop(self):
        """停止进程 — 强制终止，不依赖 _running 标志位（防止上次 stop 失败后无法重试）"""
        if not self._worker:
            return

        self.output_received.emit("\n>>> 正在停止进程...\n")
        self._worker.stop()
        if self._worker.isRunning():
            self._worker.wait(5000)
        self._running = False
        self.state_changed.emit(False)

    def wait_for_stop(self, timeout=3000):
        if self._worker and self._worker.isRunning():
            return self._worker.wait(timeout)
        return True

    def _on_output(self, line):
        self.output_received.emit(line)

    def _on_finished(self, exit_code):
        self._running = False
        self.state_changed.emit(False)
        self.finished.emit(exit_code)
