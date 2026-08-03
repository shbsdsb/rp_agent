"""会话模型与持久化:data/chats/<id>.json(基于 storage.py)。"""
from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone

from rp_agent.storage import json_read, json_write, safe_path


@dataclass
class ChatSession:
    """一次对话会话。system 消息不入库,每次请求时从 prompts 现加载。"""

    id: str
    created_at: str
    updated_at: str
    connection: str = ""            # ApiConnection.name,可为空
    messages: list[dict] = field(default_factory=list)


def _new_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + secrets.token_hex(2)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(session_id: str):
    return safe_path(f"chats/{session_id}.json")


def create_session(connection: str = "") -> ChatSession:
    now = _now()
    return ChatSession(id=_new_id(), created_at=now, updated_at=now, connection=connection)


def save_session(session: ChatSession) -> None:
    session.updated_at = _now()
    json_write(
        _path(session.id),
        {
            "id": session.id,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
            "connection": session.connection,
            "messages": session.messages,
        },
    )


def load_session(session_id: str) -> ChatSession | None:
    data = json_read(_path(session_id))
    if not isinstance(data, dict):
        return None
    try:
        return ChatSession(
            id=str(data["id"]),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            connection=str(data.get("connection", "")),
            messages=list(data.get("messages", [])),
        )
    except (KeyError, TypeError, ValueError):
        return None


def list_sessions() -> list[ChatSession]:
    sessions = []
    for p in safe_path("chats").parent.glob("chats/*.json"):
        s = load_session(p.stem)
        if s is not None:
            sessions.append(s)
    sessions.sort(key=lambda s: s.updated_at, reverse=True)
    return sessions


def append_message(session: ChatSession, role: str, content: str) -> None:
    session.messages.append({"role": role, "content": content})
    session.updated_at = _now()
