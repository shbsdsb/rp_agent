"""开发热重载:轮询(mtime)监控文件变化,分发重启/热重载回调。零依赖。"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Sequence

logger = logging.getLogger("rp_agent")


class Watcher:
    """轮询监控 .py 与配置文件。

    - py_dirs 下递归 `*.py` 变化 → on_restart()(重启子进程)
    - config_files 变化 → on_reload()(不重启,热生效)
    """

    def __init__(
        self,
        py_dirs: Sequence[Path],
        config_files: Sequence[Path],
        on_restart: Callable[[], None],
        on_reload: Callable[[], None],
        interval: float = 0.5,
    ) -> None:
        self._py_dirs = list(py_dirs)
        self._config_files = list(config_files)
        self._on_restart = on_restart
        self._on_reload = on_reload
        self._interval = interval
        self._py_snapshot: dict[Path, int] = {}
        self._config_snapshot: dict[Path, int] = {}
        self._running = False

    def _scan_py_files(self) -> dict[Path, int]:
        files: dict[Path, int] = {}
        for d in self._py_dirs:
            if not d.is_dir():
                continue
            for p in d.rglob("*.py"):
                try:
                    files[p] = p.stat().st_mtime_ns
                except OSError:
                    continue
        return files

    def _scan_config_files(self) -> dict[Path, int]:
        files: dict[Path, int] = {}
        for p in self._config_files:
            try:
                files[p] = p.stat().st_mtime_ns
            except OSError:
                continue
        return files

    @staticmethod
    def _changed_files(
        now: dict[Path, int], prev: dict[Path, int]
    ) -> set[Path]:
        added = set(now) - set(prev)
        removed = set(prev) - set(now)
        modified = {k for k in now if k in prev and now[k] != prev[k]}
        return added | removed | modified

    def _check(self) -> None:
        py_now = self._scan_py_files()
        if py_now != self._py_snapshot:
            changed = self._changed_files(py_now, self._py_snapshot)
            logger.info("[watch] 检测到代码变更: %s", sorted(str(p) for p in changed))
            self._py_snapshot = py_now
            self._on_restart()

        cfg_now = self._scan_config_files()
        if cfg_now != self._config_snapshot:
            changed = self._changed_files(cfg_now, self._config_snapshot)
            logger.info("[watch] 检测到配置变更: %s", sorted(str(p) for p in changed))
            self._config_snapshot = cfg_now
            self._on_reload()

    def run(self) -> None:
        """阻塞轮询,直到 stop() 或 KeyboardInterrupt。"""
        self._py_snapshot = self._scan_py_files()
        self._config_snapshot = self._scan_config_files()
        self._running = True
        try:
            while self._running:
                time.sleep(self._interval)
                self._check()
        except KeyboardInterrupt:
            self._running = False

    def stop(self) -> None:
        self._running = False
