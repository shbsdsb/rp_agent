"""日志初始化:标准库 logging,输出到 stderr,格式固定。"""
from __future__ import annotations

import logging
import sys

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
