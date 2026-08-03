# API 连接命令集重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 `api` 命令集:参数解析器(长/短选项)、list/get/add/del/test 升级、新增 pull/sync/modify(含 nano 风格交互编辑)、密钥脱敏、`last_tested`/`models_endpoint` 字段、`list_models` 端点。

**Architecture:** 新增 `api/args.py`(轻量参数解析);`models.py`/`store.py` 扩展字段与 `mask_key`;`client.py` 新增 `list_models` 并让 `chat`/`test_connection` 支持 timeout 覆盖;`shell.py` 重构 `_cmd_api`(parse_args 接入 + 错误捕获 + 新命令)与 `_modify_interactive`(prompt_toolkit key_bindings/bottom_toolbar)。

**Tech Stack:** Python 3.14、prompt_toolkit 3.0.53(已引入)、标准库、pytest。

## Global Constraints

- Python >= 3.14;测试一律 `uv run pytest`(Windows,不用 python3)
- 不新增依赖(prompt_toolkit 已引入);`uv.lock` 不变
- 位置参数新顺序:`add <name> <base_url> <api_key> [model]`(旧顺序已废弃,仅新顺序+弃用警告)
- 密钥脱敏:`mask_key`(≤8 → `****`;否则前4+****+后4);显示一律脱敏
- `last_tested` 用 UTC ISO 时间(`datetime.now(timezone.utc).isoformat()`)
- `--filter`/`--set` 支持多次(AND/多字段),值不允许空格
- 现有 69 项测试:api 相关重构更新,其余保持
- 工作分支 `feat/api-command-refactor`

---

### Task 1: `api/args.py` 参数解析器

**Files:**
- Create: `src/rp_agent/api/args.py`
- Create: `tests/test_args.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `parse_args(argv: list[str]) -> tuple[dict[str, object], list[str]]`:选项 dict(key 为长选项去 `--`;`filter`/`set` 为 `list[str]`;无值选项值为 `""`)+ 位置参数列表;未知选项/缺值抛 `ValueError`

- [ ] **Step 1: 写失败测试 `tests/test_args.py`**

```python
import pytest

from rp_agent.api.args import parse_args


def test_named_options():
    opts, pos = parse_args(
        ["--name", "demo", "--url", "https://x/v1", "--key", "k", "--model", "m"]
    )
    assert opts == {"name": "demo", "url": "https://x/v1", "key": "k", "model": "m"}
    assert pos == []


def test_flag_and_positional():
    opts, pos = parse_args(["demo", "--verbose"])
    assert opts == {"verbose": ""}
    assert pos == ["demo"]


def test_short_options():
    opts, _ = parse_args(["-v"])
    assert opts == {"verbose": ""}
    opts, _ = parse_args(["-f"])
    assert opts == {"force": ""}
    opts, _ = parse_args(["-t", "5"])
    assert opts == {"timeout": "5"}


def test_filter_and_set_multiple():
    opts, _ = parse_args(
        ["--filter", "model=gpt-4", "--filter", "base_url=x", "--set", "model=gpt-5"]
    )
    assert opts["filter"] == ["model=gpt-4", "base_url=x"]
    assert opts["set"] == ["model=gpt-5"]


def test_unknown_option_raises():
    with pytest.raises(ValueError, match="未知选项"):
        parse_args(["--wat"])


def test_missing_value_raises():
    with pytest.raises(ValueError, match="缺少值"):
        parse_args(["--name"])
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_args.py -v
```
Expected: FAIL(`ModuleNotFoundError: No module named 'rp_agent.api.args'`)

- [ ] **Step 3: 写 `src/rp_agent/api/args.py`**

```python
"""API 子命令参数解析器(轻量,零依赖)。"""
from __future__ import annotations

_SHORT_OPTS = {
    "-v": "--verbose",
    "-f": "--force",
    "-m": "--modify",
    "-t": "--timeout",
}
_VALUE_OPTS = {"--name", "--url", "--key", "--model", "--timeout"}
_LIST_OPTS = {"--filter", "--set"}


def parse_args(argv: list[str]) -> tuple[dict[str, object], list[str]]:
    """解析 --key value / --flag / 短选项 / 位置参数。

    - 取值选项:--name/--url/--key/--model/--timeout(缺值抛 ValueError)
    - 列表选项:--filter/--set 可多次,收集为 list
    - 无值选项:--verbose/--force/--modify/--pull/--set-default → ""
    - 短选项经 _SHORT_OPTS 映射;未知 --xxx 抛 ValueError
    """
    opts: dict[str, object] = {}
    positional: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        long = _SHORT_OPTS.get(tok, tok)
        if long.startswith("--"):
            if long in _LIST_OPTS:
                if i + 1 >= len(argv):
                    raise ValueError(f"选项 {tok} 缺少值")
                opts.setdefault(long[2:], []).append(argv[i + 1])
                i += 2
            elif long in _VALUE_OPTS:
                if i + 1 >= len(argv):
                    raise ValueError(f"选项 {tok} 缺少值")
                opts[long[2:]] = argv[i + 1]
                i += 2
            else:
                opts[long[2:]] = ""
                i += 1
            continue
        if tok.startswith("-") and len(tok) > 1:
            raise ValueError(f"未知选项: {tok}")
        positional.append(tok)
        i += 1
    return opts, positional
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_args.py -v
```
Expected: 6 passed

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/api/args.py tests/test_args.py
git commit -m "feat: api 参数解析器(args.py:长/短选项/列表选项/错误)"
```

---

### Task 2: `models.py`/`store.py` 扩展字段与 `mask_key`

**Files:**
- Modify: `src/rp_agent/api/models.py`
- Modify: `src/rp_agent/api/store.py`
- Modify: `tests/test_models.py`
- Modify: `tests/test_store.py`

**Interfaces:**
- Consumes: 现有 `ApiConnection`、store 函数
- Produces:
  - `ApiConnection` 新增 `models_endpoint: str = "/models"`、`last_tested: str = ""`
  - `mask_key(key: str) -> str`(在 models.py)
  - store 读写新字段;旧文件兼容(缺失字段默认)

- [ ] **Step 1: 追加失败测试**

`tests/test_models.py` 追加:
```python
from rp_agent.api.models import ApiConnection, mask_key


def test_new_fields_defaults():
    conn = ApiConnection(name="d", base_url="https://x", api_key="k", model="m")
    assert conn.models_endpoint == "/models"
    assert conn.last_tested == ""


def test_mask_key():
    assert mask_key("sk-1234567890abcdef") == "sk-1****cdef"
    assert mask_key("short") == "****"  # 长度 <= 8
    assert mask_key("") == "****"
```

`tests/test_store.py` 追加:
```python
def test_roundtrip_new_fields(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    conn = ApiConnection(
        name="d", base_url="https://x/v1", api_key="k", model="m",
        models_endpoint="/custom-models", last_tested="2026-08-03T00:00:00+00:00",
    )
    save_connection(conn)
    loaded = get_connection("d")
    assert loaded is not None
    assert loaded.models_endpoint == "/custom-models"
    assert loaded.last_tested == "2026-08-03T00:00:00+00:00"


def test_old_file_backward_compat(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    # 写入无新字段的旧格式文件
    (tmp_path / "api").mkdir(parents=True, exist_ok=True)
    (tmp_path / "api" / "old.json").write_text(
        '{"name": "old", "base_url": "https://x", "api_key": "k", "model": "m"}',
        encoding="utf-8",
    )
    loaded = get_connection("old")
    assert loaded is not None
    assert loaded.models_endpoint == "/models"
    assert loaded.last_tested == ""
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_models.py tests/test_store.py -v
```
Expected: 新增测试 FAIL(`AttributeError: 'ApiConnection' object has no attribute 'models_endpoint'`)

- [ ] **Step 3: 修改实现**

`models.py`:
```python
@dataclass
class ApiConnection:
    name: str
    base_url: str
    api_key: str
    model: str
    timeout: float = 30.0
    models_endpoint: str = "/models"
    last_tested: str = ""

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


def mask_key(key: str) -> str:
    """密钥脱敏:长度<=8 显示 ****;否则 前4 + **** + 后4。"""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"
```

`store.py` 的 `get_connection` 返回值与 `save_connection` 数据字典追加字段:
```python
        return ApiConnection(
            name=str(data.get("name") or name),
            base_url=str(data["base_url"]),
            api_key=str(data.get("api_key", "")),
            model=str(data["model"]),
            timeout=float(data.get("timeout", 30.0)),
            models_endpoint=str(data.get("models_endpoint", "/models")),
            last_tested=str(data.get("last_tested", "")),
        )
```
```python
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
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_models.py tests/test_store.py -v
```
Expected: 全部通过(models 原 6 + 新 2 = 8;store 原 2 + 新 2 = 4)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/api/models.py src/rp_agent/api/store.py tests/test_models.py tests/test_store.py
git commit -m "feat: 连接字段扩展(models_endpoint/last_tested)+ mask_key 脱敏"
```

---

### Task 3: `client.py` — `list_models` 与 timeout 覆盖

**Files:**
- Modify: `src/rp_agent/api/client.py`
- Modify: `src/rp_agent/api/__init__.py`
- Modify: `tests/test_client.py`

**Interfaces:**
- Consumes: `ApiConnection`(Task 2 含 models_endpoint)
- Produces:
  - `chat(conn, messages, *, timeout: float | None = None, **kwargs) -> str`
  - `test_connection(conn, timeout: float | None = None) -> str`
  - `list_models(conn, timeout: float | None = None) -> list[str]`
  - `__init__` 导出 `list_models`

- [ ] **Step 1: 追加失败测试 `tests/test_client.py`**

```python
def test_list_models_success(fake_server):
    _FakeHandler.method = "GET"
    _FakeHandler.status = 200
    _FakeHandler.body = {"data": [{"id": "gpt-4"}, {"id": "gpt-3.5"}]}
    conn = _conn(fake_server)
    models = list_models(conn)
    assert models == ["gpt-4", "gpt-3.5"]


def test_list_models_custom_endpoint(fake_server):
    _FakeHandler.method = "GET"
    _FakeHandler.status = 200
    _FakeHandler.body = {"data": [{"id": "m1"}]}
    conn = _conn(fake_server, models_endpoint="/v1/custom")
    assert list_models(conn) == ["m1"]


def test_list_models_unauthorized(fake_server):
    _FakeHandler.method = "GET"
    _FakeHandler.status = 401
    _FakeHandler.body = {"error": "no"}
    with pytest.raises(ApiError, match="认证失败"):
        list_models(_conn(fake_server))
```

假服务器需支持 GET:在 `_FakeHandler` 加 `do_GET`(与 do_POST 相同逻辑,记录 `captured` 为空 dict 即可,因为 GET 无 body)。

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_client.py -v
```
Expected: 新增 FAIL(`ImportError: cannot import name 'list_models'`)

- [ ] **Step 3: 修改 `client.py`**

`chat` 签名与 urlopen 超时:
```python
def chat(
    conn: ApiConnection,
    messages: list[dict],
    *,
    timeout: float | None = None,
    **kwargs: object,
) -> str:
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
        with urllib.request.urlopen(req, timeout=timeout or conn.timeout) as resp:
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


def test_connection(conn: ApiConnection, timeout: float | None = None) -> str:
    """发最小消息验证连接,返回模型回复。"""
    return chat(conn, [{"role": "user", "content": "ping"}], timeout=timeout)


def list_models(conn: ApiConnection, timeout: float | None = None) -> list[str]:
    """GET {base_url}/{models_endpoint},解析 data[].id。"""
    url = conn.base_url.rstrip("/") + "/" + conn.models_endpoint.lstrip("/")
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {conn.api_key}"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or conn.timeout) as resp:
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
        return [str(item["id"]) for item in payload["data"]]
    except (KeyError, TypeError) as exc:
        raise ApiError(f"响应格式异常,缺少 data[].id: {payload}") from exc
```

`__init__.py` 导出追加:
```python
from rp_agent.api.client import ApiError, chat, list_models, test_connection
__all__ = ["ApiConnection", "ApiError", "chat", "list_models", "test_connection"]
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_client.py -v
```
Expected: 全部通过(原 4 + 新 3 = 7)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/api/client.py src/rp_agent/api/__init__.py tests/test_client.py
git commit -m "feat: client.list_models + chat/test_connection 支持 timeout 覆盖"
```

---

### Task 4: `shell.py` — `_cmd_api` 重构(list/get/add/del/test/pull/sync/modify --set)

**Files:**
- Modify: `src/rp_agent/shell.py`
- Modify: `tests/test_shell.py`

**Interfaces:**
- Consumes: `parse_args`(Task 1)、`ApiConnection`/`mask_key`(Task 2)、store 函数、`list_models`/`test_connection`/`ApiError`(Task 3)
- Produces: `_cmd_api(args)` 完整重构;`_modify_interactive(conn: ApiConnection) -> None` 占位(本任务仅调用,Task 5 实现)

- [ ] **Step 1: 重构 `_cmd_api`(替换现函数)**

`shell.py` 顶部 import 追加:
```python
from datetime import datetime, timezone

from rp_agent.api.args import parse_args
from rp_agent.api.models import ApiConnection, mask_key
```

`_cmd_api` 整体替换(核心逻辑):
```python
def _cmd_api(args: list[str]) -> None:
    if not args:
        print(f"用法: {_colorize_usage('api <list|get|add|del|test|pull|sync|modify> ...')}")
        return
    sub = args[0]
    try:
        _dispatch_api(sub, args[1:])
    except ValueError as exc:
        print(f"参数错误: {exc}")
    except ApiError as exc:
        print(f"API 错误: {exc}")


def _dispatch_api(sub: str, rest: list[str]) -> None:
    if sub == "list":
        _api_list(rest)
    elif sub == "get":
        _api_get(rest)
    elif sub == "add":
        _api_add(rest)
    elif sub == "del":
        _api_del(rest)
    elif sub == "test":
        _api_test(rest)
    elif sub == "pull":
        _api_pull(rest)
    elif sub == "sync":
        _api_sync(rest)
    elif sub == "modify":
        _api_modify(rest)
    else:
        print(f"未知子命令: {sub}(用法: api <list|get|add|del|test|pull|sync|modify> ...)")
```

各子实现(完整代码):
```python
def _api_list(rest: list[str]) -> None:
    opts, _ = parse_args(rest)
    conns = [c for n in list_connections() if (c := get_connection(n)) is not None]
    filters = opts.get("filter", [])
    if isinstance(filters, str):
        filters = [filters]
    for f in filters:
        if "=" not in f:
            print(f"[警告] 忽略非法筛选: {f}(应为 k=v)")
            continue
        k, v = f.split("=", 1)
        conns = [c for c in conns if str(getattr(c, k, "")).startswith(v)]
    if not conns:
        print("(无连接)")
        return
    if "verbose" in opts:
        for c in conns:
            print(f"{c.name}\t{c.base_url}\t{c.model}\t{c.last_tested or '-'}")
    else:
        for c in conns:
            print(f"  {c.name}")


def _api_get(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api get <name>")
        return
    conn = get_connection(pos[0])
    if conn is None:
        print(f"连接不存在: {pos[0]}")
        return
    print(f"name={conn.name}")
    print(f"base_url={conn.base_url}")
    print(f"api_key={mask_key(conn.api_key) if conn.api_key else '(空)'}")
    print(f"model={conn.model}")
    print(f"timeout={conn.timeout}")
    print(f"models_endpoint={conn.models_endpoint}")
    print(f"last_tested={conn.last_tested or '(未测试)'}")


def _api_add(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    name = opts.get("name") or (pos[0] if pos else None)
    url = opts.get("url") or (pos[1] if len(pos) > 1 else None)
    key = opts.get("key") or (pos[2] if len(pos) > 2 else None)
    model = opts.get("model") or (pos[3] if len(pos) > 3 else "")
    if not (name and url and key):
        print("用法: api add --name <name> --url <base_url> --key <api_key> [--model <model>]")
        print("  或(弃用) api add <name> <base_url> <api_key> [model]")
        return
    if pos:
        print("[弃用] 位置参数形式将移除,请改用 --name/--url/--key/--model")
    if get_connection(name) is not None and "modify" not in opts:
        print(f"连接已存在: {name}(使用 api modify {name} 或 api add --modify ... 覆盖)")
        return
    conn = ApiConnection(name=name, base_url=url, api_key=key, model=model)
    if "pull" in opts:
        try:
            models = list_models(conn)
            print(f"拉取到模型: {', '.join(models)}")
        except ApiError as exc:
            print(f"[警告] 拉取模型失败({exc}),仍保存连接(可后续 api pull)")
    try:
        save_connection(conn)
        print(f"已保存连接: {name}")
    except ValueError as exc:
        print(f"配置无效: {exc}")


def _api_del(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api del <name> [-f]")
        return
    name = pos[0]
    if "force" not in opts:
        ans = input(f"确认删除连接 {name}? [y/N]: ").strip()
        if ans.lower() not in ("y", "yes"):
            print("已取消")
            return
    if delete_connection(name):
        print(f"已删除连接: {name}")
    else:
        print(f"连接不存在: {name}")


def _api_test(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api test <name> [--timeout <秒>]")
        return
    conn = get_connection(pos[0])
    if conn is None:
        print(f"连接不存在: {pos[0]}")
        return
    timeout = float(opts.get("timeout", conn.timeout))
    print(f"正在测试连接: {conn.name} ({conn.base_url})…")
    try:
        test_connection(conn, timeout=timeout)
        conn.last_tested = datetime.now(timezone.utc).isoformat()
        save_connection(conn)
        print("连接正常")
    except ApiError as exc:
        print(f"测试失败: {exc}")


def _api_pull(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if pos:
        conn = get_connection(pos[0])
        if conn is None:
            print(f"连接不存在: {pos[0]}")
            return
    elif "url" in opts and "key" in opts:
        conn = ApiConnection(name="(临时)", base_url=opts["url"], api_key=opts["key"], model="")
        try:
            conn.validate()
        except ValueError as exc:
            print(f"URL 无效: {exc}")
            return
    else:
        print("用法: api pull <name> [--set-default] | api pull --url <base_url> --key <api_key> [--timeout <秒>]")
        return
    timeout = float(opts.get("timeout", conn.timeout))
    try:
        models = list_models(conn, timeout=timeout)
        for i, m in enumerate(models, 1):
            print(f"  {i}. {m}")
        if "set-default" in opts and models and pos:
            conn.model = models[0]
            save_connection(conn)
            print(f"已将默认模型设为: {models[0]}")
    except ApiError as exc:
        print(f"拉取失败: {exc}")


def _api_sync(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api sync <name> [--set-default]")
        return
    conn = get_connection(pos[0])
    if conn is None:
        print(f"连接不存在: {pos[0]}")
        return
    try:
        test_connection(conn)
        models = list_models(conn)
        print("测试通过,模型列表:")
        for i, m in enumerate(models, 1):
            print(f"  {i}. {m}")
        conn.last_tested = datetime.now(timezone.utc).isoformat()
        if "set-default" in opts and models:
            conn.model = models[0]
            print(f"已将默认模型设为: {models[0]}")
        save_connection(conn)
    except ApiError as exc:
        print(f"同步失败: {exc}")


def _api_modify(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api modify <name> [--set field=value ...]")
        return
    conn = get_connection(pos[0])
    if conn is None:
        print(f"连接不存在: {pos[0]}")
        return
    sets = opts.get("set", [])
    if isinstance(sets, str):
        sets = [sets]
    if sets:
        _api_modify_set(conn, sets)
    else:
        _modify_interactive(conn)


def _api_modify_set(conn: ApiConnection, sets: list[str]) -> None:
    """非交互 --set:先验证全部,再原子更新。"""
    updates: dict[str, object] = {}
    for s in sets:
        if "=" not in s:
            print(f"非法 --set: {s}(应为 field=value)")
            return
        k, v = s.split("=", 1)
        if k not in ("base_url", "api_key", "model", "timeout", "models_endpoint"):
            print(f"未知字段: {k}")
            return
        updates[k] = v
    for k, v in updates.items():
        if k == "base_url" and not (
            v.startswith("http://") or v.startswith("https://")
        ):
            print(f"base_url 无效: {v}")
            return
        if k == "timeout":
            try:
                float(v)
            except ValueError:
                print(f"timeout 无效: {v}")
                return
    for k, v in updates.items():
        setattr(conn, k, float(v) if k == "timeout" else v)
    save_connection(conn)
    print(f"已更新连接: {conn.name}")
```

- [ ] **Step 2: 追加/重构 `tests/test_shell.py`**

```python
def test_shell_api_add_exists_without_modify(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed([
        "api add --name d --url https://x/v1 --key k --model m",
        "api add --name d --url https://x/v1 --key k --model m",
        "exit",
    ]))
    out = capsys.readouterr().out
    assert "已保存连接" in out
    assert "连接已存在" in out


def test_shell_api_add_modify_overwrites(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed([
        "api add --name d --url https://x/v1 --key k --model m",
        "api add --modify --name d --url https://x/v2 --key k2 --model m2",
        "exit",
    ]))
    out = capsys.readouterr().out
    assert "已保存连接" in out
    conn = get_connection("d")
    assert conn is not None and conn.base_url == "https://x/v2"


def test_shell_api_get_masks_key(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed([
        "api add --name d --url https://x/v1 --key sk-1234567890abcdef --model m",
        "api get d",
        "exit",
    ]))
    out = capsys.readouterr().out
    assert "sk-1****cdef" in out
    assert "sk-1234567890abcdef" not in out


def test_shell_api_modify_set_atomic(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed([
        "api add --name d --url https://x/v1 --key k --model m",
        "api modify d --set model=gpt-5 --set badfield=1",
        "api get d",
        "exit",
    ]))
    out = capsys.readouterr().out
    assert "未知字段" in out
    assert "model=gpt-5" not in out  # 原子:未写入


def test_shell_api_del_confirm(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed([
        "api add --name d --url https://x/v1 --key k --model m",
        "n",
        "exit",
    ]))  # 注意:del 确认需注入;见下
```
**说明**:`del` 的确认用 `input()`,测试中 `_feed` 注入的输入会先被主循环消费。为可靠测试 del,改为确认函数可注入:`_confirm(prompt)` 模块函数,`_api_del` 调用它;测试 monkeypatch `rp_agent.shell._confirm` 返回 "y"/"n"。

`_api_del` 改为:
```python
def _confirm(prompt: str) -> str:
    """交互确认(可被测试 monkeypatch)。"""
    return input(prompt).strip()


def _api_del(rest: list[str]) -> None:
    opts, pos = parse_args(rest)
    if not pos:
        print("用法: api del <name> [-f]")
        return
    name = pos[0]
    if "force" not in opts:
        ans = _confirm(f"确认删除连接 {name}? [y/N]: ")
        if ans.lower() not in ("y", "yes"):
            print("已取消")
            return
    if delete_connection(name):
        print(f"已删除连接: {name}")
    else:
        print(f"连接不存在: {name}")
```

del 测试:
```python
def test_shell_api_del_confirm_decline(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    monkeypatch.setattr("rp_agent.shell._confirm", lambda _p: "n")
    run_shell(_feed([
        "api add --name d --url https://x/v1 --key k --model m",
        "api del d",
        "api get d",
        "exit",
    ]))
    out = capsys.readouterr().out
    assert "已取消" in out
    assert get_connection("d") is not None  # 未删除


def test_shell_api_del_force(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed([
        "api add --name d --url https://x/v1 --key k --model m",
        "api del d -f",
        "api get d",
        "exit",
    ]))
    out = capsys.readouterr().out
    assert "已删除连接" in out
    assert "连接不存在" in out
```

- [ ] **Step 3: 运行测试确认通过**

```bash
uv run pytest tests/test_shell.py -v
```
Expected: 原 api 相关测试(test_shell_api_add_and_get 用旧位置参数,需更新为命名参数)+ 新测试全部通过。`test_shell_api_add_and_get` 更新为:
```python
def test_shell_api_add_and_get(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed([
        "api add --name demo --url http://localhost:8000/v1 --key k --model gpt-4o",
        "api get demo",
        "exit",
    ]))
    out = capsys.readouterr().out
    assert "已保存连接" in out
    assert "base_url=http://localhost:8000/v1" in out
    assert "api_key=****" in out  # key "k" 长度<=8
```

- [ ] **Step 4: 提交**

```bash
git add src/rp_agent/shell.py tests/test_shell.py
git commit -m "feat: _cmd_api 重构(list/get/add/del/test/pull/sync/modify --set)"
```
注:本任务 `_modify_interactive` 尚未定义,`_api_modify` 无 `--set` 时调用它会导致 NameError —— 因此在 Task 4 提交前先放一个占位实现(见 Task 5 Step 0),或把 `_api_modify` 无 `--set` 分支临时改为打印提示。**采用后者**:本任务 `_api_modify` 无 `--set` 时 `print("交互模式待 Task 5 实现,请用 --set")`;Task 5 替换。

---

### Task 5: modify 交互式编辑(nano 快捷键)

**Files:**
- Modify: `src/rp_agent/shell.py`
- Modify: `tests/test_shell.py`

**Interfaces:**
- Consumes: `_api_modify`(Task 4)、`ApiConnection`/`mask_key`(Task 2)
- Produces:
  - `_prompt_field(label: str, current: str, secret: bool) -> tuple[str, str]`:(text, action),action ∈ {"normal", "save", "cancel"}(可被测试 monkeypatch)
  - `_modify_interactive(conn: ApiConnection) -> None`
  - `_api_modify` 无 `--set` 时调用 `_modify_interactive`

- [ ] **Step 0: 在 Task 4 提交前将 `_api_modify` 的无 --set 分支保留为占位**（如上,Task 4 已处理;本任务替换）

- [ ] **Step 1: 追加失败测试 `tests/test_shell.py`**

```python
def test_modify_interactive_save(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    # 注入 _prompt_field 模拟:每字段输入新值后 Ctrl+O 保存
    responses = iter([
        ("https://new/v1", "normal"),
        ("newkey", "normal"),
        ("gpt-5", "save"),
    ])
    monkeypatch.setattr(
        "rp_agent.shell._prompt_field",
        lambda _l, _c, _s: next(responses),
    )
    run_shell(_feed([
        "api add --name d --url https://x/v1 --key k --model m",
        "api modify d",
        "api get d",
        "exit",
    ]))
    out = capsys.readouterr().out
    assert "已保存" in out
    conn = get_connection("d")
    assert conn is not None
    assert conn.base_url == "https://new/v1"
    assert conn.model == "gpt-5"


def test_modify_interactive_cancel(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    monkeypatch.setattr(
        "rp_agent.shell._prompt_field",
        lambda _l, _c, _s: ("", "cancel"),
    )
    run_shell(_feed([
        "api add --name d --url https://x/v1 --key k --model m",
        "api modify d",
        "api get d",
        "exit",
    ]))
    out = capsys.readouterr().out
    assert "已放弃修改" in out
    conn = get_connection("d")
    assert conn is not None and conn.model == "m"  # 未修改
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_shell.py -v
```
Expected: FAIL(`NameError: name '_modify_interactive' is not defined`)

- [ ] **Step 3: 实现 `_prompt_field` 与 `_modify_interactive`**

`shell.py` import 追加:
```python
from prompt_toolkit.key_binding import KeyBindings
```

```python
def _prompt_field(label: str, current: str, secret: bool) -> tuple[str, str]:
    """询问一个字段。返回 (text, action):action ∈ normal/save/cancel。"""
    from prompt_toolkit.shortcuts import prompt as pt_prompt

    kb = KeyBindings()
    state: dict[str, str] = {"action": "normal"}

    @kb.add("c-o")
    def _on_save(event):
        state["action"] = "save"
        event.app.exit(result=event.current_buffer.text)

    @kb.add("c-x")
    def _on_cancel(event):
        state["action"] = "cancel"
        event.app.exit(result=event.current_buffer.text)

    shown = mask_key(current) if secret and current else current
    try:
        text = pt_prompt(
            f"{label} (回车保留: {shown}): ",
            is_password=secret,
            key_bindings=kb,
            bottom_toolbar="^O 保存   ^X 放弃   /url /key /model 跳转字段",
        )
    except KeyboardInterrupt:
        return "", "cancel"
    return text, state["action"]


def _modify_interactive(conn: ApiConnection) -> None:
    """交互式编辑:nano 风格(Ctrl+O 保存 / Ctrl+X 放弃)+ 字段跳转。"""
    fields = [
        ("base_url", "Base URL", False),
        ("api_key", "API Key", True),
        ("model", "Model", False),
    ]
    values: dict[str, str] = {
        "base_url": conn.base_url,
        "api_key": conn.api_key,
        "model": conn.model,
    }
    current = 0
    while True:
        field, label, secret = fields[current]
        text, action = _prompt_field(label, values[field], secret)
        if action == "cancel":
            print("已放弃修改")
            return
        if text.startswith("/"):
            target = text[1:].lower()
            names = {f[0]: i for i, f in enumerate(fields)}
            if target in names:
                current = names[target]
                continue
            print(f"未知字段: {target}(可用: /url /key /model)")
            continue
        if text == "":
            text = values[field]  # 回车保留原值
        if field == "base_url" and not (
            text.startswith("http://") or text.startswith("https://")
        ):
            print("Base URL 无效,需以 http(s):// 开头")
            continue
        values[field] = text
        if action == "save":
            for k, v in values.items():
                setattr(conn, k, v)
            save_connection(conn)
            print("已保存")
            return
        current = (current + 1) % len(fields)
```

`_api_modify` 无 `--set` 分支替换为 `_modify_interactive(conn)`。

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_shell.py -v
```
Expected: 全部通过(含新增 modify 交互 2 项)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/shell.py tests/test_shell.py
git commit -m "feat: modify 交互式编辑(nano 快捷键 Ctrl+O/X + 字段跳转 /field)"
```

---

### Task 6: help_data 更新 + 全量验证 + 收尾

**Files:**
- Modify: `src/rp_agent/help_data.py`
- Modify: `README.md`

**Interfaces:**
- Consumes: 全部 Task 1-5 产物
- Produces: 全绿测试套件 + 完整 git 历史

- [ ] **Step 1: 更新 `help_data.py` 的 api 条目**

```python
    {
        "command": "api",
        "aliases": [],
        "desc": "API 连接管理(api list/get/add/del/test/pull/sync/modify)",
        "usage": "api <list|get|add|del|test|pull|sync|modify> ...",
        "params": [
            ("list [-v] [--filter k=v]", "列出连接(详细视图/筛选)"),
            ("get <name>", "查看连接详情(密钥脱敏)"),
            ("add --name N --url U --key K [--model M] [--modify] [--pull]", "新建/覆盖连接"),
            ("del <name> [-f]", "删除连接(默认二次确认)"),
            ("test <name> [--timeout N]", "测试连接连通性"),
            ("pull <name> [--set-default] | pull --url U --key K", "拉取模型列表"),
            ("sync <name> [--set-default]", "测试并拉取模型"),
            ("modify <name> [--set field=value ...]", "交互或非交互修改"),
        ],
    },
```

- [ ] **Step 2: 运行全量测试**

```bash
uv run pytest -v
```
Expected: 全部通过(原 69 + 新增 args 6 + models 2 + store 2 + client 3 + shell 若干;以实际为准)

- [ ] **Step 3: 更新 README.md 的 API 连接章节**

```markdown
shell 命令:`api list [-v] [--filter k=v]` / `api get <name>` /
`api add --name N --url U --key K [--model M] [--modify] [--pull]` /
`api del <name> [-f]` / `api test <name> [--timeout N]` /
`api pull <name> [--set-default]` / `api sync <name> [--set-default]` /
`api modify <name> [--set field=value]`(交互模式支持 Ctrl+O 保存/Ctrl+X 放弃,/url /key /model 跳转)。
密钥显示脱敏;`api test`/`sync` 记录 `last_tested`。
```

- [ ] **Step 4: 确认工作树整洁并提交收尾**

```bash
git status --short
git add -A
git commit -m "chore: API 命令重构完成(help/README 更新)"
git log --oneline
```

---

## 验收清单(对照 spec 修订版 v2)

- [ ] `parse_args`:长/短选项、`--filter`/`--set` 多次、未知选项 ValueError → spec §3.1
- [ ] `ApiConnection` 含 `models_endpoint`/`last_tested`;旧文件兼容 → spec §3.4
- [ ] `mask_key` 边界(≤8 → `****`)→ spec §3.5
- [ ] `list_models` 可配端点;`chat`/`test_connection` timeout 覆盖 → spec §3.3
- [ ] `add` 新顺序位置参数 + 弃用警告;`--modify` 覆盖;已存在报错;`--pull` 失败警告仍保存 → spec §3.2、§4
- [ ] `del` 二次确认(`-f` 跳过);`get` 脱敏;`test` 更新 last_tested → spec §3.2
- [ ] `pull`/`sync`(`--set-default` 直接设定) → spec §3.2
- [ ] `modify --set` 原子更新(先验证后写入) → spec §3.7
- [ ] modify 交互:nano 快捷键(Ctrl+O/X)+ 字段跳转 + 底部提示栏 → spec §3.6
- [ ] 错误统一捕获(ValueError/ApiError,不堆栈) → spec §4
- [ ] 不新增依赖;现有非 api 测试保持 → spec §7
