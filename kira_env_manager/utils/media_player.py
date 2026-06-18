"""背景音乐播放器 — 封装 QMediaPlayer 自动循环播放"""

from pathlib import Path

from PyQt5.QtCore import QObject, QUrl
from PyQt5.QtMultimedia import QMediaPlayer, QMediaContent

from kira_env_manager.common.constants import MUSIC_FILE_PATH, MUSIC_DEFAULT_VOLUME


class MusicPlayer(QObject):
    """低音量自动循环背景音乐播放器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._player = QMediaPlayer(self)
        self._player.setVolume(MUSIC_DEFAULT_VOLUME)  # 15%
        self._player.mediaStatusChanged.connect(self._on_media_status)

        # 加载音乐文件：优先用户配置，其次内置默认
        self._current_path = self._resolve_path()
        url = QUrl.fromLocalFile(str(self._current_path))
        self._player.setMedia(QMediaContent(url))
        self._player.play()

    @staticmethod
    def _resolve_path():
        """按优先级解析音乐文件路径"""
        from kira_env_manager.common.config import get as cfg_get
        custom = cfg_get("music_path")
        if custom:
            p = Path(custom) if isinstance(custom, str) else custom
            if p.exists():
                return p
        return Path(MUSIC_FILE_PATH)

    def load_file(self, path):
        """切换到指定音乐文件并开始播放"""
        p = Path(path)
        if not p.exists():
            return False
        self._current_path = p
        url = QUrl.fromLocalFile(str(p))
        self._player.setMedia(QMediaContent(url))
        self._player.play()
        return True

    def _on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            self._player.play()

    def toggle_playback(self):
        """切换播放/暂停，返回 True=播放中, False=已暂停"""
        if self._player.state() == QMediaPlayer.PlayingState:
            self._player.pause()
        else:
            self._player.play()
        return self._player.state() == QMediaPlayer.PlayingState

    @property
    def is_playing(self):
        return self._player.state() == QMediaPlayer.PlayingState
