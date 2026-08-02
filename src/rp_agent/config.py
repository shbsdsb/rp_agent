"""全局配置:从环境变量读取,模块级单例。"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_LOG_LEVEL = "INFO"
ENV_LOG_LEVEL = "RP_AGENT_LOG_LEVEL"


@dataclass
class AppConfig:
    """应用配置。骨架阶段仅含日志级别,后续按需扩展字段。"""

    log_level: str = DEFAULT_LOG_LEVEL


_config: AppConfig | None = None


def get_config(force_reload: bool = False) -> AppConfig:
    """返回全局配置单例。

    force_reload=True 时忽略缓存,重新从环境变量构造(用于测试与运行时覆盖)。
    """
    global _config
    if _config is None or force_reload:
        _config = AppConfig(
            log_level=os.environ.get(ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL),
        )
    return _config
