# api list 默认连接标记 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `api list` 对全局默认连接(`api use` 设置)显示 `*` 标记 + 黄色高亮。

**Architecture:** store 层新增轻量 `get_default_name()`(只读 `default_connection.json` 的 `name` 字段,不加载连接、不打日志,与 `connection_exists` 同哲学),`get_default_connection` 重构复用;shell 层 `_api_list` 在普通/verbose 视图对默认连接的 name 列加 `*` 与 `term.yellow` 高亮。

**Tech Stack:** Python 3.14、UV、pytest、ANSI 颜色(term.yellow)。

## Global Constraints

- 只用 UV(`uv run pytest` 跑测试);Python >= 3.14
- 数据读写统一走 `storage.py` / `rp_agent.api.store`;shell 不直接碰文件路径
- 轻量查询哲学:`get_default_name` 不得触发 `json_read` 对缺失文件的"读取 JSON 失败"WARNING(上一轮已确立的 `connection_exists` 模式)
- `ShellLexer` 与 `_COMMAND_ARGS`/`_VALID_OPTIONS`/`_KNOWN_COMMANDS` 定义不得改动
- 分支 `feat/api-list-default` 上小步提交;每步提交只 add 本任务文件
- 测试驱动:先写失败测试再实现

---

### Task 1: store 层 `get_default_name()`

**Files:**
- Modify: `src/rp_agent/api/store.py`(新增 `get_default_name`,重构 `get_default_connection`)
- Test: `tests/test_store.py`(新增用例 + import)

**Interfaces:**
- Consumes: `_default_conn_path()`、`json_read`(store.py 既有)、`get_connection`(store.py 既有)
- Produces: `get_default_name() -> str | None` —— Task 2 的 `_api_list` 依赖;重构后的 `get_default_connection()` 行为不变(既有测试必须保持通过)

- [ ] **Step 1: 写失败测试**

在 `tests/test_store.py` 的 import 中加入 `get_default_name`,并追加用例:

```python
from rp_agent.api.store import (
    connection_exists,
    delete_connection,
    get_connection,
    get_default_connection,
    get_default_name,
    list_connections,
    save_connection,
    set_default_connection,
)
```

```python
def test_get_default_name_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    assert get_default_name() is None  # 未设置
    set_default_connection("d")
    assert get_default_name() == "d"


def test_get_default_name_empty_and_corrupt(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    set_default_connection("")  # 空名
    assert get_default_name() is None
    (tmp_path / "default_connection.json").write_text("not a dict", encoding="utf-8")
    assert get_default_name() is None  # 损坏文件 → None,不崩溃
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_store.py::test_get_default_name_roundtrip tests/test_store.py::test_get_default_name_empty_and_corrupt -v`
Expected: FAIL —— `ImportError: cannot import name 'get_default_name'`

- [ ] **Step 3: 实现**

在 `src/rp_agent/api/store.py` 的 `get_default_connection` 之前新增,并重构它:

```python
def get_default_name() -> str | None:
    """当前默认连接名:仅读 default_connection.json 的 name 字段,不加载连接。"""
    ensure_dirs()
    path = _default_conn_path()
    if not path.exists():
        return None  # 未设置默认连接是常态,不告警
    data = json_read(path)
    if not isinstance(data, dict):
        return None
    name = str(data.get("name", ""))
    return name or None


def get_default_connection() -> ApiConnection | None:
    name = get_default_name()
    return get_connection(name) if name else None
```

(删除原 `get_default_connection` 中重复的 `path.exists()`/`json_read` 逻辑)

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS(新增 2 个 + 既有全部,包括 `test_default_connection_roundtrip` 等)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/api/store.py tests/test_store.py
git commit -m "feat: store 新增 get_default_name 轻量查询"
```

---

### Task 2: `_api_list` 显示默认标记 + help 文案

**Files:**
- Modify: `src/rp_agent/shell.py`(`_api_list` + store import 加 `get_default_name`)
- Modify: `src/rp_agent/help_data.py`(`api list` 描述)
- Test: `tests/test_shell.py`(新增用例)

**Interfaces:**
- Consumes: `get_default_name()`(Task 1)、`yellow`(shell.py 已导入)、`get_connection`/`list_connections`(既有)
- Produces: `api list` / `api list -v` 输出中默认连接显示 `name *`(黄色高亮)

- [ ] **Step 1: 写失败测试**

在 `tests/test_shell.py` 末尾追加:

```python
def test_shell_api_list_marks_default(capsys, monkeypatch, tmp_path):
    """api list 对全局默认连接显示 * 标记,非默认不标记。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api add --name e --url https://y/v2 --key k2 --model m2",
                "api use d",
                "api list",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "d *" in out
    assert "e *" not in out


def test_shell_api_list_no_default_no_star(capsys, monkeypatch, tmp_path):
    """未设置默认连接 → 列表无星号。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api list",
                "exit",
            ]
        )
    )
    assert "*" not in capsys.readouterr().out


def test_shell_api_list_verbose_marks_default(capsys, monkeypatch, tmp_path):
    """verbose 视图同样标记默认连接。"""
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(
        _feed(
            [
                "api add --name d --url https://x/v1 --key k --model m",
                "api use d",
                "api list -v",
                "exit",
            ]
        )
    )
    out = capsys.readouterr().out
    assert "d *" in out


def test_shell_api_list_default_deleted_no_warning(
    capsys, monkeypatch, tmp_path, caplog
):
    """默认连接指向已删除连接 → 无星号、无"读取 JSON 失败"告警。"""
    import logging

    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    with caplog.at_level(logging.WARNING, logger="rp_agent"):
        run_shell(
            _feed(
                [
                    "api add --name d --url https://x/v1 --key k --model m",
                    "api use d",
                    "api del d -f",
                    "api list",
                    "exit",
                ]
            )
        )
    out = capsys.readouterr().out
    assert "*" not in out
    assert "读取 JSON 失败" not in caplog.text
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_shell.py -q -k "api_list" -v`
Expected: FAIL —— 新 4 个用例中除 `no_default_no_star` 外均失败(`d *` 未出现)

- [ ] **Step 3: 实现**

`src/rp_agent/shell.py` 的 store import 块加入 `get_default_name`:

```python
from rp_agent.api.store import (
    connection_exists,
    delete_connection,
    get_connection,
    get_default_name,
    list_connections,
    save_connection,
    set_default_connection,
)
```

`_api_list` 改为(仅替换 `if "verbose" in opts:` 起的打印段,并在 `if not conns` 之前取默认名):

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
    default_name = get_default_name()
    if "verbose" in opts:
        for c in conns:
            name_col = yellow(f"{c.name} *") if c.name == default_name else c.name
            print(f"{name_col}\t{c.base_url}\t{c.model}\t{c.last_tested or '-'}")
    else:
        for c in conns:
            if c.name == default_name:
                print(f"  {yellow(c.name + ' *')}")
            else:
                print(f"  {c.name}")
```

`src/rp_agent/help_data.py` 的 `api list` 描述更新:

```python
            ("list [-v] [--filter k=v]", "列出连接(默认连接以 * 标记)"),
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_shell.py -q -k "api_list" -v`
Expected: PASS(4 个新用例)

- [ ] **Step 5: 全量回归 + 冒烟**

Run: `uv run pytest -q`
Expected: PASS(全部测试;工作区若存在未提交的 `prompts/system/chat.txt` 改动,test_chat 中 2 个既有失败与之相关、与本任务无关)

Run: `printf "api add --name dd --url https://x/v1 --key k --model m\napi use dd\napi list\napi del dd -f\nexit\n" | uv run rp-agent shell`
Expected: `api list` 输出 `dd *`(黄色),删除后列表为空

- [ ] **Step 6: 提交**

```bash
git add src/rp_agent/shell.py src/rp_agent/help_data.py tests/test_shell.py
git commit -m "feat: api list 显示默认连接 * 标记(黄色高亮)"
```
