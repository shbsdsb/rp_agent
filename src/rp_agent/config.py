"""全局配置:JSON 配置文件 + 环境变量加载,模块级单例,支持热重载。

优先级:环境变量(RP_AGENT_LOG_LEVEL)> 配置文件(log_level)> 默认值(INFO)。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("rp_agent")

DEFAULT_LOG_LEVEL = "INFO"
ENV_LOG_LEVEL = "RP_AGENT_LOG_LEVEL"
DEFAULT_CONFIG_PATH = Path(__file__).parent / "configs" / "app.json"


@dataclass
class AppConfig:
    """应用配置。骨架阶段仅含日志级别,后续按需扩展字段。"""

    log_level: str = DEFAULT_LOG_LEVEL


_config: AppConfig | None = None


def load_config_file(path: Path | None = None) -> dict[str, object]:
    """读取 JSON 配置文件。缺失/损坏时返回 {} 并告警,不崩溃。"""
    cfg_path = path or DEFAULT_CONFIG_PATH
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("配置文件读取失败(%s): %s,回退默认值", cfg_path, exc)
        return {}


def _merge_config(file_data: dict[str, object]) -> AppConfig:
    """合并优先级:环境变量 > 配置文件 > 默认值。"""
    log_level = DEFAULT_LOG_LEVEL
    file_level = file_data.get("log_level")
    if isinstance(file_level, str) and file_level:
        log_level = file_level
    env_level = os.environ.get(ENV_LOG_LEVEL)
    if env_level:
        log_level = env_level
    return AppConfig(log_level=log_level)


def reload_config() -> bool:
    """重新加载配置(文件 + env),更新单例;返回配置是否发生变化。"""
    global _config
    new_config = _merge_config(load_config_file())
    changed = _config is None or new_config != _config
    _config = new_config
    return changed


def get_config(force_reload: bool = False) -> AppConfig:
    """返回全局配置单例。force_reload=True 时强制重新加载。"""
    if _config is None or force_reload:
        reload_config()
    assert _config is not None
    return _config
