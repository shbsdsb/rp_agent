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


def get_connection(name: str) -> ApiConnection | None:
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
