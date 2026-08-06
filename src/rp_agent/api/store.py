"""API 连接配置持久化(基于 storage.py)。"""
from __future__ import annotations

import logging
from pathlib import Path

from rp_agent.api.models import ApiConnection
from rp_agent.storage import API_DIR, ensure_dirs, json_read, json_write, safe_path

logger = logging.getLogger("rp_agent")


def _conn_path(name: str) -> Path:
    return safe_path(f"api/{name}.json")


def list_connections() -> list[str]:
    ensure_dirs()
    if not API_DIR.is_dir():
        return []
    return sorted(p.stem for p in API_DIR.glob("*.json"))


def connection_exists(name: str) -> bool:
    """连接是否已存在:仅查文件名,不读内容、不打日志(区别于 get_connection)。"""
    if not name:
        return False
    ensure_dirs()
    return _conn_path(name).exists()


def get_connection(name: str) -> ApiConnection | None:
    if not name:
        return None  # 空名直接返回,避免拼出 api/.json 触发文件读取告警
    ensure_dirs()
    data = json_read(_conn_path(name))
    if not isinstance(data, dict):
        return None
    try:
        return ApiConnection(
            name=str(data.get("name") or name),
            base_url=str(data["base_url"]),
            api_key=str(data.get("api_key", "")),
            model=str(data["model"]),
            timeout=float(data.get("timeout", 30.0)),
            models_endpoint=str(data.get("models_endpoint", "/models")),
            last_tested=str(data.get("last_tested", "")),
        )
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("连接配置损坏(%s): %s", name, exc)
        return None


def save_connection(conn: ApiConnection) -> None:
    conn.validate()
    ensure_dirs()
    json_write(
        _conn_path(conn.name),
        {
            "name": conn.name,
            "base_url": conn.base_url,
            "api_key": conn.api_key,
            "model": conn.model,
            "timeout": conn.timeout,
            "models_endpoint": conn.models_endpoint,
            "last_tested": conn.last_tested,
        },
    )


def delete_connection(name: str) -> bool:
    ensure_dirs()
    try:
        _conn_path(name).unlink()
        return True
    except FileNotFoundError:
        return False
    except OSError as exc:
        logger.error("删除连接失败(%s): %s", name, exc)
        return False


def _default_conn_path() -> Path:
    # data 根,避免与 API_DIR.glob("*.json") 的 list_connections 冲突
    return safe_path("default_connection.json")


def get_default_connection() -> ApiConnection | None:
    ensure_dirs()
    path = _default_conn_path()
    if not path.exists():
        return None  # 未设置默认连接是常态,不告警
    data = json_read(path)
    if not isinstance(data, dict):
        return None
    name = str(data.get("name", ""))
    return get_connection(name) if name else None


def set_default_connection(name: str) -> None:
    ensure_dirs()
    json_write(_default_conn_path(), {"name": name})
