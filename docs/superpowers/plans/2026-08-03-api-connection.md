# API 连接链路实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 API 连接链路:`data/api/<name>.json` 连接配置管理(models+store)+ OpenAI 兼容真实调用(client)+ shell 集成(api list/get/add/del/test)。

**Architecture:** 新增 `src/rp_agent/api/` 包三模块:`models.py`(`ApiConnection` dataclass + validate)、`store.py`(基于 `storage.py` 的增删改查)、`client.py`(标准库 `urllib` 调 OpenAI 兼容 `chat/completions`);`shell.py` 加 `api` 命令分发。测试用标准库 `http.server` 起本地假 OpenAI 服务器。

**Tech Stack:** Python 3.14、标准库(urllib/json/http.server/threading)、pytest。

## Global Constraints

- Python >= 3.14;测试一律 `uv run pytest`(Windows,不用 python3)
- 不新增依赖(禁止 requests/openai 等);`uv.lock` 不变
- 连接文件:`data/api/<name>.json`,路径经 `storage.safe_path` 防穿越;api_key 明文(用户已确认)
- 配置校验:`validate()` 抛 `ValueError`;base_url 必须以 `http://`/`https://` 开头
- 现有 36 项测试保持通过
- 工作分支 `feat/api-connection`

---

### Task 1: `api/models.py` + `api/store.py` — 连接模型与持久化

**Files:**
- Create: `src/rp_agent/api/__init__.py`
- Create: `src/rp_agent/api/models.py`
- Create: `src/rp_agent/api/store.py`
- Create: `tests/test_models.py`
- Create: `tests/test_store.py`

**Interfaces:**
- Consumes: `from rp_agent.storage import API_DIR, ensure_dirs, json_read, json_write, safe_path`(现有)
- Produces:
  - `ApiConnection(name: str, base_url: str, api_key: str, model: str, timeout: float = 30.0)`;`validate() -> None` 抛 `ValueError`
  - `list_connections() -> list[str]`、`get_connection(name: str) -> ApiConnection | None`、`save_connection(conn: ApiConnection) -> None`、`delete_connection(name: str) -> bool`
  - `api/__init__.py` 导出 `ApiConnection`、`ApiError`(ApiError 在 client.py 定义,Task 2;本任务先导出 ApiConnection)

- [ ] **Step 1: 写失败测试 `tests/test_models.py` 与 `tests/test_store.py`**

`tests/test_models.py`:
```python
import pytest

from rp_agent.api.models import ApiConnection


def _conn(**overrides):
    params = dict(
        name="demo",
        base_url="https://api.openai.com/v1",
        api_key="sk-x",
        model="gpt-4o",
    )
    params.update(overrides)
    return ApiConnection(**params)


def test_default_timeout():
    assert _conn().timeout == 30.0


def test_validate_ok():
    _conn().validate()  # 不抛错


@pytest.mark.parametrize(
    "overrides",
    [{"name": ""}, {"base_url": "ftp://x"}, {"model": ""}, {"timeout": 0}],
)
def test_validate_invalid(overrides):
    with pytest.raises(ValueError):
        _conn(**overrides).validate()
```

`tests/test_store.py`:
```python
from rp_agent.api.models import ApiConnection
from rp_agent.api.store import (
    delete_connection,
    get_connection,
    list_connections,
    save_connection,
)


def test_save_get_list_delete_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    conn = ApiConnection(
        name="demo",
        base_url="https://api.openai.com/v1",
        api_key="sk-x",
        model="gpt-4o",
    )
    save_connection(conn)
    assert list_connections() == ["demo"]
    loaded = get_connection("demo")
    assert loaded is not None
    assert loaded.base_url == "https://api.openai.com/v1"
    assert loaded.model == "gpt-4o"
    assert delete_connection("demo") is True
    assert get_connection("demo") is None
    assert delete_connection("demo") is False
    assert list_connections() == []


def test_get_missing_returns_none(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    assert get_connection("nope") is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_models.py tests/test_store.py -v
```
Expected: FAIL(`ModuleNotFoundError: No module named 'rp_agent.api'`)

- [ ] **Step 3: 写实现文件**

`src/rp_agent/api/__init__.py`:
```python
"""API 连接链路:配置管理(models/store)+ 真实调用(client)。"""
from rp_agent.api.models import ApiConnection

__all__ = ["ApiConnection"]
```

`src/rp_agent/api/models.py`:
```python
"""API 连接数据模型。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ApiConnection:
    """OpenAI 兼容 API 连接配置。"""

    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float = 30.0

    def validate(self) -> None:
        """校验字段;非法抛 ValueError。"""
        if not self.name:
            raise ValueError("连接名不能为空")
        if not (
            self.base_url.startswith("http://")
            or self.base_url.startswith("https://")
        ):
            raise ValueError(
                f"base_url 必须以 http:// 或 https:// 开头: {self.base_url}"
            )
        if not self.model:
            raise ValueError("模型名不能为空")
        if self.timeout <= 0:
            raise ValueError(f"timeout 必须为正数: {self.timeout}")
```

`src/rp_agent/api/store.py`:
```python
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_models.py tests/test_store.py -v
```
Expected: 7 passed(models 5 + store 2)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/api tests/test_models.py tests/test_store.py
git commit -m "feat: API 连接模型与持久化(api/models.py + store.py)"
```

---

### Task 2: `api/client.py` — OpenAI 兼容客户端

**Files:**
- Create: `src/rp_agent/api/client.py`
- Create: `tests/test_client.py`

**Interfaces:**
- Consumes: `ApiConnection`(Task 1)
- Produces:
  - `class ApiError(Exception)`
  - `chat(conn: ApiConnection, messages: list[dict], **kwargs: object) -> str`
  - `test_connection(conn: ApiConnection) -> str`
  - `api/__init__.py` 追加导出 `ApiError`、`chat`、`test_connection`

- [ ] **Step 1: 写失败测试 `tests/test_client.py`**

```python
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from rp_agent.api.client import ApiError, chat, test_connection
from rp_agent.api.models import ApiConnection


class _FakeHandler(BaseHTTPRequestHandler):
    status = 200
    body: dict = {}
    captured: dict = {}

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        self.__class__.captured = json.loads(raw)
        self.send_response(self.__class__.status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.__class__.body).encode("utf-8"))

    def log_message(self, *args):
        pass


@pytest.fixture()
def fake_server():
    server = HTTPServer(("127.0.0.1", 0), _FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def _conn(server):
    return ApiConnection(
        name="test",
        base_url=f"http://127.0.0.1:{server.server_port}/v1",
        api_key="sk-test",
        model="test-model",
    )


def test_chat_success(fake_server):
    _FakeHandler.status = 200
    _FakeHandler.body = {"choices": [{"message": {"content": "你好"}}]}
    reply = chat(_conn(fake_server), [{"role": "user", "content": "hi"}])
    assert reply == "你好"
    assert _FakeHandler.captured["model"] == "test-model"
    assert _FakeHandler.captured["messages"] == [{"role": "user", "content": "hi"}]


def test_chat_unauthorized(fake_server):
    _FakeHandler.status = 401
    _FakeHandler.body = {"error": "unauthorized"}
    with pytest.raises(ApiError, match="认证失败"):
        chat(_conn(fake_server), [{"role": "user", "content": "hi"}])


def test_chat_connection_failed():
    conn = ApiConnection(
        name="t",
        base_url="http://127.0.0.1:1/v1",  # 不可达端口
        api_key="k",
        model="m",
        timeout=0.5,
    )
    with pytest.raises(ApiError, match="连接失败"):
        chat(conn, [{"role": "user", "content": "hi"}])


def test_test_connection(fake_server):
    _FakeHandler.status = 200
    _FakeHandler.body = {"choices": [{"message": {"content": "pong"}}]}
    assert test_connection(_conn(fake_server)) == "pong"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_client.py -v
```
Expected: FAIL(`ModuleNotFoundError: No module named 'rp_agent.api.client'`)

- [ ] **Step 3: 写 `src/rp_agent/api/client.py` 并更新 `__init__.py`**

`src/rp_agent/api/client.py`:
```python
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
```

`src/rp_agent/api/__init__.py`(整体替换):
```python
"""API 连接链路:配置管理(models/store)+ 真实调用(client)。"""
from rp_agent.api.client import ApiError, chat, test_connection
from rp_agent.api.models import ApiConnection

__all__ = ["ApiConnection", "ApiError", "chat", "test_connection"]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_client.py -v
```
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/api tests/test_client.py
git commit -m "feat: OpenAI 兼容客户端(api/client.py + 本地假服务器测试)"
```

---

### Task 3: Shell 集成 `api` 命令组

**Files:**
- Modify: `src/rp_agent/shell.py`
- Modify: `tests/test_shell.py`

**Interfaces:**
- Consumes: `list_connections`、`get_connection`、`save_connection`、`delete_connection`(Task 1)、`test_connection`、`ApiError`(Task 2)、`ApiConnection`(Task 1)
- Produces: shell `api` 命令(子命令 list/get/add/del/test),注册进 `_COMMANDS`

- [ ] **Step 1: 追加失败测试 `tests/test_shell.py`**

```python
def test_shell_api_list_empty(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["api list", "exit"]))
    out = capsys.readouterr().out
    assert "(无连接)" in out


def test_shell_api_add_and_get(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add demo http://localhost:8000/v1 gpt-4o",
                "api get demo",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "已保存连接" in out
    assert "base_url=http://localhost:8000/v1" in out
    assert "api_key=(空)" in out
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_shell.py -v
```
Expected: FAIL(新测试报"未知命令: api")

- [ ] **Step 3: 在 `src/rp_agent/shell.py` 加 `_cmd_api` 并注册**

在 `_cmd_history` 后追加:
```python
def _cmd_api(args: list[str]) -> None:
    if not args:
        print("用法: api <list|get|add|del|test> ...")
        return
    sub = args[0]
    if sub == "list":
        names = list_connections()
        if not names:
            print("(无连接)")
            return
        for n in names:
            print(f"  {n}")
    elif sub == "get":
        if len(args) < 2:
            print("用法: api get <name>")
            return
        conn = get_connection(args[1])
        if conn is None:
            print(f"连接不存在: {args[1]}")
            return
        key = conn.api_key
        masked = key[:3] + "***" if key else "(空)"
        print(f"name={conn.name}")
        print(f"base_url={conn.base_url}")
        print(f"api_key={masked}")
        print(f"model={conn.model}")
        print(f"timeout={conn.timeout}")
    elif sub == "add":
        if len(args) < 4:
            print("用法: api add <name> <base_url> <model> [api_key]")
            return
        conn = ApiConnection(
            name=args[1],
            base_url=args[2],
            model=args[3],
            api_key=args[4] if len(args) > 4 else "",
        )
        try:
            save_connection(conn)
            print(f"已保存连接: {conn.name}")
        except ValueError as exc:
            print(f"配置无效: {exc}")
    elif sub == "del":
        if len(args) < 2:
            print("用法: api del <name>")
            return
        if delete_connection(args[1]):
            print(f"已删除连接: {args[1]}")
        else:
            print(f"连接不存在: {args[1]}")
    elif sub == "test":
        if len(args) < 2:
            print("用法: api test <name>")
            return
        conn = get_connection(args[1])
        if conn is None:
            print(f"连接不存在: {args[1]}")
            return
        print(f"正在测试连接: {conn.name} ({conn.base_url})…")
        try:
            print(f"模型回复: {test_connection(conn)}")
        except ApiError as exc:
            print(f"测试失败: {exc}")
    else:
        print(f"未知子命令: {sub}(用法: api <list|get|add|del|test> ...)")
```

更新 import(顶部 `from rp_agent.api.models import ApiConnection` 与 `from rp_agent.api.store import ...`、`from rp_agent.api.client import ApiError, test_connection`):
```python
from rp_agent.api.client import ApiError, test_connection
from rp_agent.api.models import ApiConnection
from rp_agent.api.store import (
    delete_connection,
    get_connection,
    list_connections,
    save_connection,
)
```

`_COMMANDS` 追加:
```python
    "api": ("API 连接管理(api list/get/add/del/test)", _cmd_api),
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_shell.py -v
```
Expected: 7 passed(原 5 + 新 2)

- [ ] **Step 5: 手动冒烟**

```bash
printf "api list\napi add demo http://localhost:8000/v1 gpt-4o\napi get demo\napi del demo\nexit\n" | uv run rp-agent shell
```
Expected: 依次输出 (无连接)/已保存连接/get 详情/api_key=(空)/已删除连接/退出。

- [ ] **Step 6: 提交**

```bash
git add src/rp_agent/shell.py tests/test_shell.py
git commit -m "feat: shell 集成 api 命令组(list/get/add/del/test)"
```

---

### Task 4: 全量验证与收尾

**Files:**
- Modify: `README.md`(补充 API 连接说明)

**Interfaces:**
- Consumes: Task 1-3 产物
- Produces: 全绿测试套件 + 完整 git 历史

- [ ] **Step 1: 运行全量测试**

```bash
uv run pytest -v
```
Expected: 49 passed(36 原有 + 5 models + 2 store + 4 client + 2 shell)

- [ ] **Step 2: 更新 README.md(在"交互式 Shell"章节后追加)**

```markdown
## API 连接

连接配置存于 `data/api/<name>.json`(明文 api_key,不入 git):

```bash
uv run rp-agent shell
rp-agent> api add openai https://api.openai.com/v1 gpt-4o sk-xxx
rp-agent> api test openai
```

shell 命令:`api list` / `api get <name>` / `api add <name> <base_url> <model> [api_key]` / `api del <name>` / `api test <name>`(OpenAI 兼容)。
```

- [ ] **Step 3: 确认工作树整洁并提交收尾**

```bash
git status --short
git add -A
git commit -m "chore: API 连接链路完成(README 更新)"
git log --oneline
```
Expected: `git log --oneline` 显示连续提交历史。

---

## 验收清单(对照 spec)

- [ ] `ApiConnection` validate:base_url http(s)、name/model 非空、timeout 正数 → spec §3.2
- [ ] store 增删改查:save/get/list/delete,缺失返回 None → spec §3.3
- [ ] `chat` 真实调用:POST chat/completions、Bearer 认证、解析 content → spec §3.4
- [ ] 错误分类:认证失败(401/403)/连接失败/响应格式异常(ApiError)→ spec §3.4、§4
- [ ] shell `api list/get/add/del/test`,api_key 打码 → spec §3.5
- [ ] 不新增依赖;现有 36 项测试保持通过,总计 49 passed → spec §7
