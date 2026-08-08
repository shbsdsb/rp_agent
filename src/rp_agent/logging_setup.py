"""日志初始化:标准库 logging,输出到 stderr,格式固定。"""
from __future__ import annotations

import logging
import sys
from typing import Callable

LOGGER_NAME = "rp_agent"
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """初始化 rp_agent 根 logger。幂等:已存在 handler 时不重复添加。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)


class _EmitHandler(logging.Handler):
    """把日志记录转发给 emit 回调(TUI 输出区用),避免直写 stderr 污染屏幕。"""

    def __init__(self, emit_fn: Callable[[str], None]) -> None:
        super().__init__()
        self._emit_fn = emit_fn

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._emit_fn(self.format(record))
        except Exception:
            self.handleError(record)


_original_handlers: list[logging.Handler] | None = None


def install_emit_handler(emit_fn: Callable[[str], None]) -> None:
    """TUI 下把 rp_agent logger 的 handler 换成走 emit_fn 的 handler。

    全屏 Application 运行时,stderr 直写会污染输入行/破坏渲染状态,
    日志改经 emit 进入输出区。幂等:已安装时不重复。
    """
    global _original_handlers
    logger = logging.getLogger(LOGGER_NAME)
    if _original_handlers is not None:
        return
    _original_handlers = logger.handlers[:]
    logger.handlers = []
    handler = _EmitHandler(emit_fn)
    handler.setFormatter(logging.Formatter(_FORMAT))
    logger.addHandler(handler)


def uninstall_emit_handler() -> None:
    """恢复原始 handlers(TUI 退出时)。"""
    global _original_handlers
    logger = logging.getLogger(LOGGER_NAME)
    if _original_handlers is None:
        return
    logger.handlers = _original_handlers
    _original_handlers = None
