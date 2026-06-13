"""多实例管理器 — 支持同时运行多个 KiraAI 进程"""

import copy

from PyQt5.QtCore import QObject, pyqtSignal

from kira_env_manager.utils.process_manager import ProcessManager
from kira_env_manager.utils.helpers import check_port_open


class KiraInstance(QObject):
    """单个 KiraAI 实例"""

    output_line = pyqtSignal(str)       # 控制台输出
    state_changed = pyqtSignal(bool)    # 运行/停止
    finished = pyqtSignal(int)          # 退出码
    port_changed = pyqtSignal(int)      # 新增: 端口变更

    def __init__(self, cfg, parent=None):
        """
        cfg: dict with keys:
            name, port (int), data_dir (str), project_path (str), extra_args (list)
        """
        super().__init__(parent)
        self.cfg = cfg
        self._pm = ProcessManager(self)
        self._running = False

        self._pm.output_received.connect(self.output_line)
        self._pm.state_changed.connect(self._on_state)
        self._pm.finished.connect(self._on_finished)

    @property
    def name(self):
        return self.cfg.get("name", "default")

    @name.setter
    def name(self, value):
        self.cfg["name"] = value

    @property
    def port(self):
        return self.cfg.get("port", 5267)

    @property
    def data_dir(self):
        return self.cfg.get("data_dir", "")

    @property
    def project_path(self):
        return self.cfg.get("project_path", "")

    def is_running(self):
        """通过端口检测是否在运行"""
        return check_port_open("127.0.0.1", self.port)

    def start(self, python_exe):
        """启动该实例

        Args:
            python_exe: Python 可执行文件路径
        """
        import os

        cmd = [python_exe, "main.py"]
        extra = self.cfg.get("extra_args", [])
        if extra:
            cmd.extend(extra)

        # 数据目录
        env = {}
        data_dir = self.data_dir
        if data_dir:
            env["KIRA_DATA_DIR"] = data_dir

        # 确保 data 目录存在
        if data_dir and not os.path.exists(data_dir):
            os.makedirs(data_dir, exist_ok=True)

        cwd = self.project_path
        self.output_line.emit(
            f"\n=== {self.name} (端口:{self.port}) ===\n"
            f">>> {' '.join(cmd)}\n"
            f">>> cwd: {cwd}\n"
            f">>> data: {data_dir or '(default)'}\n\n"
        )
        return self._pm.start(cmd, cwd=cwd, env=env)

    def stop(self):
        self._pm.stop()

    def _on_state(self, running):
        self._running = running
        self.state_changed.emit(running)

    def _on_finished(self, exit_code):
        self._running = False
        self.finished.emit(exit_code)


class InstanceManager(QObject):
    """管理所有 KiraAI 实例"""

    instances_changed = pyqtSignal()  # 列表变化
    any_output = pyqtSignal(str)      # 任何实例的输出

    def __init__(self, parent=None):
        super().__init__(parent)
        self._instances = []         # list of KiraInstance
        self._active_instance = None  # 当前选中/关注的实例

    def add(self, cfg):
        """添加实例

        cfg keys: name, port, data_dir, project_path, extra_args
        """
        cfg = dict(cfg)

        # 检查名称唯一性，自动添加后缀
        name = cfg.get("name", "default")
        existing_names = {inst.name for inst in self._instances}
        if name in existing_names:
            suffix = 2
            while f"{name}_{suffix}" in existing_names:
                suffix += 1
            cfg["name"] = f"{name}_{suffix}"

        inst = KiraInstance(cfg, self)
        inst.output_line.connect(lambda line, inst=inst: self._on_inst_output(inst, line))
        inst.state_changed.connect(lambda _: self.instances_changed.emit())
        inst.finished.connect(lambda _: self.instances_changed.emit())

        self._instances.append(inst)
        self.instances_changed.emit()
        return inst

    def remove(self, index):
        """删除指定索引的实例

        先停止进程，再从列表移除。如果 stop() 后 worker 仍未结束，
        通过 finished 信号延迟 deleteLater，不在列表移除前连接信号以避免悬空引用。
        """
        if not (0 <= index < len(self._instances)):
            return
        inst = self._instances[index]
        # stop() 内部已发出 taskkill + 500ms wait，绝大多数情况同步结束
        inst.stop()
        if inst._pm._worker and inst._pm._worker.isRunning():
            # worker 未能及时结束：连接 finished 信号延迟清理，但仍从列表移除
            # finished 最多触发一次，lambda 持有 inst 引用是安全的（不会被重复 deleteLater）
            inst._pm._worker.finished.connect(lambda: inst.deleteLater())
        else:
            inst.deleteLater()

        if self._active_instance is inst:
            self._active_instance = None
        self._instances.pop(index)
        self.instances_changed.emit()

    def remove_by_name(self, name):
        idx = self.index_of(name)
        if idx is not None:
            self.remove(idx)

    def index_of(self, name):
        """根据名称查找实例索引"""
        for i, inst in enumerate(self._instances):
            if inst.name == name:
                return i
        return None

    def clear(self):
        """停止并清空所有实例"""
        for inst in list(self._instances):
            inst.stop()
            # stop() 已处理终止逻辑，这里只做最终等待
            if inst._pm._worker and inst._pm._worker.isRunning():
                inst._pm.wait_for_stop(1000)
            inst.deleteLater()
        self._instances.clear()
        self._active_instance = None
        self.instances_changed.emit()

    def instance(self, index):
        if 0 <= index < len(self._instances):
            return self._instances[index]
        return None

    def instance_by_name(self, name):
        for inst in self._instances:
            if inst.name == name:
                return inst
        return None

    def instances(self):
        return list(self._instances)

    def count(self):
        return len(self._instances)

    def running_count(self):
        return sum(1 for inst in self._instances if inst.is_running())

    def running_instances(self):
        return [i for i in self._instances if i.is_running()]

    def set_active(self, instance):
        self._active_instance = instance

    def get_active(self):
        if self._active_instance and self._active_instance in self._instances:
            return self._active_instance
        if self._instances:
            return self._instances[-1]
        return None

    def to_config_list(self):
        """导出为可序列化的配置列表"""
        return [copy.deepcopy(inst.cfg) for inst in self._instances]

    def load_from_config(self, configs):
        """从配置列表加载实例（清空现有）"""
        self.clear()
        for cfg in configs:
            self.add(dict(cfg))

    def _on_inst_output(self, instance, line):
        # 添加实例名称前缀
        prefixed_line = f"[{instance.name}] {line}"
        self.any_output.emit(prefixed_line)
