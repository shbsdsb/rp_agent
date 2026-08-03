"""全局配置:JSON 配置文件 + 环境变量加载,模块级单例,支持热重载。

优先级:环境变量(RP_AGENT_LOG_LEVEL)> 配置文件(log_level)> 默认值(INFO)。
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from rp_agent.storage import json_write

logger = logging.getLogger("rp_agent")

DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_TIMEOUT = 300.0
ENV_LOG_LEVEL = "RP_AGENT_LOG_LEVEL"
ENV_TIMEOUT = "RP_AGENT_TIMEOUT"
DEFAULT_CONFIG_PATH = Path(__file__).parent / "configs" / "app.json"


@dataclass
class AppConfig:
    """应用配置:日志级别 + 全局网络超时(秒)。"""

    log_level: str = DEFAULT_LOG_LEVEL
    timeout: float = DEFAULT_TIMEOUT


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

    timeout = DEFAULT_TIMEOUT
    file_timeout = file_data.get("timeout")
    if isinstance(file_timeout, (int, float)) and file_timeout > 0:
        timeout = float(file_timeout)
    env_timeout = os.environ.get(ENV_TIMEOUT)
    if env_timeout:
        try:
            val = float(env_timeout)
            if val > 0:
                timeout = val
        except ValueError:
            logger.warning("环境变量 %s 非法: %s,忽略", ENV_TIMEOUT, env_timeout)
    return AppConfig(log_level=log_level, timeout=timeout)


def save_config(updates: dict[str, object], path: Path | None = None) -> None:
    """合并写入配置文件(原子写)。updates 覆盖同名字段,其余保留。"""
    cfg_path = path or DEFAULT_CONFIG_PATH
    data = load_config_file(cfg_path)
    data.update(updates)
    json_write(cfg_path, data)


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
