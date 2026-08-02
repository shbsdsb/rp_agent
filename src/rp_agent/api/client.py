"""OpenAI 兼容 API 客户端(零依赖,标准库 urllib)。"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request

from rp_agent.api.models import ApiConnection

logger = logging.getLogger("rp_agent")


class ApiError(Exception):
    """API 调用错误(连接失败/HTTP 错误/响应格式异常)。"""


def chat(conn: ApiConnection, messages: list[dict], **kwargs: object) -> str:
    """调用 OpenAI 兼容 chat/completions,返回回复文本。"""
    url = conn.base_url.rstrip("/") + "/chat/completions"
    body = {"model": conn.model, "messages": messages, **kwargs}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {conn.api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=conn.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ApiError(f"认证失败(HTTP {exc.code}): {exc.reason}") from exc
        raise ApiError(f"服务器错误(HTTP {exc.code}): {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ApiError(f"连接失败: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ApiError(f"响应不是有效 JSON: {exc}") from exc

    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ApiError(
            f"响应格式异常,缺少 choices[0].message.content: {payload}"
        ) from exc


def test_connection(conn: ApiConnection) -> str:
    """发最小消息验证连接,返回模型回复。"""
    return chat(conn, [{"role": "user", "content": "ping"}])
