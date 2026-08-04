# hotfix:help 对齐 / config help / storage 重构 + chat 命令 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** hotfix 三项:①help 概览命令名按最大宽度对齐 ②config --help 补充字段解释 ③删除 storage 命令;并扩展 chat 子命令系统(list/get/load/rename),rename 支持 prompt_toolkit tab 补全。

**Architecture:** shell.py 仿 `_cmd_api`/`_dispatch_api` 模式新增 `_cmd_chat`/`_dispatch_chat`;`chat` 命令无参仍进模式(run_shell `_MODE_COMMANDS` 分支加 `not args` 条件);`ChatSession` 加 `name` 字段(兼容旧 JSON);rename 补全用 prompt_toolkit `Completer`/`WordCompleter` 自定义触发类(仅 `chat rename` 前缀时启用)。

**Tech Stack:** Python ≥3.14、prompt_toolkit(completer 现成库)、pytest。零新依赖。

## Global Constraints

- Python >= 3.14,一律用 UV:`uv run pytest -v` 跑测试
- 交互输入必须用 prompt_toolkit(completer 属于 prompt_toolkit,不新增依赖)
- `storage.py` 底层保留(api/store、core/session 依赖);仅删除 shell 的 `storage` 命令
- 会话旧 JSON 无 `name` 字段 → 加载 `""`,兼容
- 当前分支 `hotfix`,小步提交
- 修改文件:`shell.py`、`help_data.py`、`core/session.py`、`core/chat.py` + 测试

---

### Task 1: help 概览对齐 + config help 条目 + 删 storage 命令

**Files:**
- Modify: `src/rp_agent/shell.py`(_cmd_help、_cmd_storage 删除、_COMMANDS、import)
- Modify: `src/rp_agent/help_data.py`(config 条目、删 storage 条目)
- Test: `tests/test_shell.py`、`tests/test_help_data.py`

**Interfaces:**
- Consumes: 现有 `HELP_ENTRIES`、`yellow`(term.py)、`_print_command_help`
- Produces: 无新接口;`storage` 命令从 `_COMMANDS` 移除;`config` help 条目含 3 个 params

- [ ] **Step 1: 写失败测试**

修改 `tests/test_shell.py` 第 59 行的 `test_help_lists_commands`(移除 storage):

```python
    for name in ("help", "config", "reload", "hello", "history", "exit", "chat", "rp", "agent"):
        assert name in out
```

在 `tests/test_shell.py` 末尾追加:

```python
def test_help_overview_desc_aligned(capsys):
    """help 概览 desc 同一列:不再使用 \t(短/长命令缩进不齐)。"""
    run_shell(_feed(["help", "exit"]))
    out = capsys.readouterr().out
    assert "\t" not in out


def test_storage_command_removed(capsys):
    run_shell(_feed(["storage", "exit"]))
    out = capsys.readouterr().out
    assert "未知命令: storage" in out
```

在 `tests/test_help_data.py` 末尾追加:

```python
def test_config_entry_explains_fields():
    entry = find_entry("config")
    assert entry is not None
    params_text = " ".join(p for p, _ in entry["params"])
    assert "log_level" in params_text
    assert "timeout" in params_text


def test_storage_entry_removed():
    assert find_entry("storage") is None
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_shell.py tests/test_help_data.py -q`
Expected: FAIL — `test_storage_command_removed`(storage 仍是已知命令)、`test_storage_entry_removed`(help 里仍有 storage)、`test_help_overview_desc_aligned`(仍含 `\t`)、`test_config_entry_explains_fields`(params 为空)、`test_help_lists_commands`(storage 已从断言移除但命令仍存在——该用例会因 storage 仍被列出而……不,断言只查列表内名字在 out,storage 移除断言后该用例通过;真正红的是上面 4 个)。

- [ ] **Step 3: 实现**

3a. `src/rp_agent/shell.py`:

- 第 28 行删除:`from rp_agent.storage import DATA_DIR, ensure_dirs`
- 第 94-99 行删除 `_cmd_storage` 函数
- 第 523 行 `_COMMANDS` 删除 `"storage": ("列出 data 目录内容", _cmd_storage),`
- `_cmd_help`(现第 136-147 行附近)整体替换为:

```python
def _cmd_help(args: list[str]) -> None:
    if args:
        _print_command_help(args[0])
        return
    print("可用命令:")
    names = []
    for e in HELP_ENTRIES:
        name = e["command"]
        if e["aliases"]:
            name += "/" + "/".join(e["aliases"])
        names.append(name)
    width = max(len(n) for n in names)
    for e, name in zip(HELP_ENTRIES, names):
        print(f"  {yellow(name.ljust(width))}  {e['desc']}")
    print("  输入 <命令> --help 查看详细用法")
```

3b. `src/rp_agent/help_data.py`:

- 删除 `storage` 条目(第 26-32 行)
- `config` 条目(第 12-18 行)替换为:

```python
    {
        "command": "config",
        "aliases": [],
        "desc": "显示当前配置(config timeout <秒> 可修改超时)",
        "usage": "config [timeout <秒>]",
        "params": [
            ("log_level", "日志级别:INFO/DEBUG/WARNING/ERROR(env RP_AGENT_LOG_LEVEL 覆盖)"),
            ("timeout", "全局网络超时(秒),默认 300(env RP_AGENT_TIMEOUT 覆盖)"),
            ("timeout <秒>", "设置全局超时并写入配置文件"),
        ],
    },
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_shell.py tests/test_help_data.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/shell.py src/rp_agent/help_data.py tests/test_shell.py tests/test_help_data.py
git commit -m "fix: help 概览按最大宽度对齐;config --help 补充字段解释;删除 storage 命令"
```

---

### Task 2: `ChatSession.name` 字段 + chat 业务函数(`core/session.py`、`core/chat.py`)

**Files:**
- Modify: `src/rp_agent/core/session.py`(name 字段)
- Modify: `src/rp_agent/core/chat.py`(新增函数)
- Test: `tests/test_session.py`、`tests/test_chat.py`

**Interfaces:**
- Consumes: Task 1 无关;现有 `session_store` 函数
- Produces(core/chat.py):
  - `find_session(key: str) -> ChatSession | None`(按 id 精确,或按 name 匹配;name 重名打印提示用 id)
  - `get_session(key: str) -> None`(打印会话详情含消息)
  - `load_into_session(key: str) -> ChatSession | None`(加载并打印,供 shell 赋给 _chat_session)
  - `rename_session(s: ChatSession, new_name: str) -> None`(更新 name + save;空名拒绝)
  - `rename_by_key(key: str, new_name: str) -> None`(find_session → rename_session)
  - `session_names() -> list[str]`(所有会话的 `name or id`)
  - `ChatSession.name: str = ""`(session.py)

- [ ] **Step 1: 写失败测试**

在 `tests/test_session.py` 末尾追加:

```python
def test_name_field_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    s = create_session()
    s.name = "三体讨论"
    save_session(s)
    loaded = load_session(s.id)
    assert loaded is not None and loaded.name == "三体讨论"


def test_load_old_json_without_name(monkeypatch, tmp_path):
    """旧会话 JSON 无 name 字段 → 加载 name="" 兼容。"""
    import json

    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    s = create_session()
    save_session(s)
    path = tmp_path / "chats" / f"{s.id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("name", None)
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = load_session(s.id)
    assert loaded is not None and loaded.name == ""
```

在 `tests/test_chat.py` 末尾追加:

```python
def test_find_session_by_id_and_name(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    s = create_session()
    s.name = "我的会话"
    save_session(s)
    from rp_agent.core.chat import find_session

    assert find_session(s.id).id == s.id
    assert find_session("我的会话").id == s.id
    assert find_session("nope") is None


def test_rename_session(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    from rp_agent.core.chat import rename_session

    s = create_session()
    save_session(s)
    rename_session(s, "新名字")
    assert s.name == "新名字"
    assert "已重命名" in capsys.readouterr().out
    from rp_agent.core.session import load_session

    assert load_session(s.id).name == "新名字"


def test_rename_session_empty_rejected(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    from rp_agent.core.chat import rename_session

    s = create_session()
    rename_session(s, "   ")
    assert "名称不能为空" in capsys.readouterr().out
    assert s.name == ""


def test_rename_by_key(monkeypatch, tmp_path, capsys):
    _setup(monkeypatch, tmp_path)
    from rp_agent.core.chat import rename_by_key

    s = create_session()
    save_session(s)
    rename_by_key(s.id, "重命名后")
    assert "已重命名" in capsys.readouterr().out
    from rp_agent.core.session import load_session

    assert load_session(s.id).name == "重命名后"


def test_session_names_lists_name_or_id(monkeypatch, tmp_path):
    _setup(monkeypatch, tmp_path)
    from rp_agent.core.chat import session_names

    named = create_session()
    named.name = "甲"
    save_session(named)
    unnamed = create_session()
    save_session(unnamed)
    names = session_names()
    assert "甲" in names
    assert unnamed.id in names  # 未命名显示 id
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_session.py tests/test_chat.py -q`
Expected: FAIL — `AttributeError: 'ChatSession' object has no attribute 'name'`、`ImportError: cannot import name 'find_session'`

- [ ] **Step 3: 实现**

3a. `src/rp_agent/core/session.py`:

- dataclass 增加 `name: str = ""`(在 `connection` 之后):

```python
    connection: str = ""            # ApiConnection.name,可为空
    name: str = ""                  # 可读名称,默认空(= 显示 id)
    messages: list[dict] = field(default_factory=list)
```

- `save_session` 的 JSON 增加 `"name": session.name`
- `load_session` 增加 `name=str(data.get("name", ""))`

3b. `src/rp_agent/core/chat.py` 末尾追加:

```python
def _display_key(s: session_store.ChatSession) -> str:
    return s.name or s.id


def find_session(key: str) -> session_store.ChatSession | None:
    """按 id 精确,或按 name 匹配;找不到返回 None。"""
    key = key.strip()
    for s in session_store.list_sessions():
        if s.id == key:
            return s
    matches = [s for s in session_store.list_sessions() if s.name == key]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(f"名称 {key} 对应多个会话,请改用 id(chat list 查看)")
    return None


def get_session(key: str) -> None:
    s = find_session(key)
    if s is None:
        print(f"会话不存在: {key}")
        return
    print(f"会话: {_display_key(s)} | id: {s.id}")
    print(f"连接: {s.connection or '(未设置)'} | 消息数: {len(s.messages)}")
    for i, m in enumerate(s.messages, 1):
        print(f"  [{m.get('role', '?')}] {m.get('content', '')}")


def load_into_session(key: str) -> session_store.ChatSession | None:
    s = find_session(key)
    if s is None:
        print(f"会话不存在: {key}")
        return None
    print(f"已加载会话: {_display_key(s)}")
    return s


def rename_session(s: session_store.ChatSession, new_name: str) -> None:
    new_name = new_name.strip()
    if not new_name:
        print("名称不能为空")
        return
    s.name = new_name
    session_store.save_session(s)
    print(f"已重命名: {_display_key(s)}")


def rename_by_key(key: str, new_name: str) -> None:
    s = find_session(key)
    if s is None:
        print(f"会话不存在: {key}")
        return
    rename_session(s, new_name)


def session_names() -> list[str]:
    return [_display_key(s) for s in session_store.list_sessions()]
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_session.py tests/test_chat.py -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/core/session.py src/rp_agent/core/chat.py tests/test_session.py tests/test_chat.py
git commit -m "feat: ChatSession.name 字段 + chat 业务函数(find/get/load/rename/session_names)"
```

---

### Task 3: chat 子命令系统 + /rename(shell.py、help_data.py)

**Files:**
- Modify: `src/rp_agent/shell.py`(_cmd_chat/_dispatch_chat、run_shell `_MODE_COMMANDS` 调整、`_CHAT_COMMANDS` 加 rename、`_COMMAND_ARGS["chat"]`)
- Modify: `src/rp_agent/help_data.py`(chat 条目 params)
- Test: `tests/test_shell.py`、`tests/test_shell_lexer.py`、`tests/test_help_data.py`

**Interfaces:**
- Consumes: Task 2 `_chat_business("find_session"|"get_session"|"load_into_session"|"rename_session"|"rename_by_key"|"list_sessions"|"new_session")`
- Produces:
  - `_cmd_chat(args)`、`_dispatch_chat(sub, rest)`(shell.py)
  - 模块级 `_mode_switch_request: Mode | None = None`(chat load 后切换模式用)
  - `_CHAT_COMMANDS = {"new", "list", "load", "rename"}`(chat 模式内 `/rename`)

- [ ] **Step 1: 写失败测试**

在 `tests/test_shell.py` 末尾追加:

```python
def test_shell_chat_list_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["chat list", "exit"]))
    out = capsys.readouterr().out
    assert "(无历史会话)" in out  # chat list 走子命令而非进入模式


def test_shell_chat_rename_two_args(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.core.session import create_session, save_session

    s = create_session()
    save_session(s)
    run_shell(_feed([f"chat rename {s.id} 新名", "exit"]))
    out = capsys.readouterr().out
    assert "已重命名" in out
    from rp_agent.core.session import load_session

    assert load_session(s.id).name == "新名"


def test_shell_chat_get_command(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.core.session import create_session, save_session

    s = create_session()
    save_session(s)
    run_shell(_feed([f"chat get {s.id}", "exit"]))
    assert "消息数" in capsys.readouterr().out


def test_shell_chat_load_enters_chat(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    from rp_agent.core.session import create_session, save_session

    s = create_session()
    save_session(s)
    run_shell(_feed([f"chat load {s.id}", "exit"]))
    assert "已加载会话" in capsys.readouterr().out


def test_shell_rename_in_chat_mode(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["chat", "/rename 新对话", "/exit", "exit"]))
    assert "已重命名" in capsys.readouterr().out


def test_shell_chat_unknown_subcommand(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    monkeypatch.setattr("rp_agent.api.store.API_DIR", tmp_path / "api")
    run_shell(_feed(["chat foobar", "exit"]))
    assert "未知子命令" in capsys.readouterr().out
```

在 `tests/test_shell_lexer.py` 末尾追加:

```python
def test_chat_subcommands_are_valid_params():
    for sub in ("list", "get", "load", "rename"):
        tokens = _tokens(f"chat {sub}")
        assert tokens[2] == ("class:param", sub)
```

在 `tests/test_help_data.py` 末尾追加:

```python
def test_chat_entry_explains_subcommands():
    entry = find_entry("chat")
    params_text = " ".join(p for p, _ in entry["params"])
    for sub in ("list", "get", "load", "rename"):
        assert sub in params_text
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_shell.py tests/test_shell_lexer.py tests/test_help_data.py -q`
Expected: FAIL — `chat list` 触发进入模式而非子命令;`chat rename`/`chat get` 未知子命令或未知命令;`/rename` 未知命令;lexer/help 断言失败

- [ ] **Step 3: 实现**

3a. `src/rp_agent/shell.py`:

- 模块级常量区增加 `_mode_switch_request: Mode | None = None`
- `_CHAT_COMMANDS` 改为 `{"new", "list", "load", "rename"}`
- `_COMMANDS` 增加 `"chat": ("会话管理(chat list/get/load/rename)", _cmd_chat),`
- `_COMMAND_ARGS` 增加 `"chat": {"list", "get", "load", "rename"},`
- 新增函数(放在 `_dispatch_api` 之后):

```python
def _cmd_chat(args: list[str]) -> None:
    if not args:
        print(f"用法: {_colorize_usage('chat <list|get|load|rename> ...')}")
        return
    _dispatch_chat(args[0], args[1:])


def _dispatch_chat(sub: str, rest: list[str]) -> None:
    if sub == "list":
        _chat_business("list_sessions")()
    elif sub == "get":
        if not rest:
            print("用法: chat get <id|name>")
            return
        _chat_business("get_session")(rest[0])
    elif sub == "load":
        if not rest:
            print("用法: chat load <id|name>")
            return
        _chat_load(rest[0])
    elif sub == "rename":
        _chat_rename(rest)
    else:
        print(f"未知子命令: {sub}(用法: chat <list|get|load|rename> ...)")


def _chat_load(key: str) -> None:
    global _chat_session, _mode_switch_request
    loaded = _chat_business("load_into_session")(key)
    if loaded is not None:
        _chat_session = loaded
        _mode_switch_request = "chat"


def _chat_rename(rest: list[str]) -> None:
    if len(rest) == 2:
        _chat_business("rename_by_key")(rest[0], rest[1])
    elif len(rest) == 1:
        # 交互:第二行输入新名
        new_name = _read_line(f"新名称({rest[0]}): ").strip()
        if not new_name:
            print("已取消")
            return
        _chat_business("rename_by_key")(rest[0], new_name)
    else:
        print("用法: chat rename <旧名> <新名>(旧名输入时可按 Tab 补全选择)")
```

- `run_shell` 修改:
  - `global _current_mode, _chat_session, _mode_switch_request`
  - 循环开头(`_current_mode = mode` 之后)增加:

```python
        if _mode_switch_request is not None:
            mode = _mode_switch_request
            _mode_switch_request = None
```

  - `_MODE_COMMANDS` 分支改为:

```python
        if cmd in _MODE_COMMANDS and (cmd != "chat" or not args):
            mode = _MODE_COMMANDS[cmd]
            if mode == "chat":
                _chat_session = _chat_business("new_session")()
            continue
```

  - `_CHAT_COMMANDS` 分支的 `load` 分支改为用 `_chat_load`(共享逻辑):

```python
        if mode != "home" and cmd in _CHAT_COMMANDS:
            if cmd == "new":
                _chat_session = _chat_business("new_session")()
            elif cmd == "list":
                _chat_business("list_sessions")()
            elif cmd == "load":
                if args:
                    _chat_load(args[0])
                else:
                    print("用法: /load <会话id|name>(用 /list 查看)")
            elif cmd == "rename":
                if args:
                    _chat_business("rename_session")(_chat_session, args[0])
                else:
                    print("用法: /rename <新名称>")
            continue
```

3b. `src/rp_agent/help_data.py` 的 `chat` 条目(第 73-79 行)替换为:

```python
    {
        "command": "chat",
        "aliases": [],
        "desc": "进入 AI 聊天模式;chat <子命令> 管理会话",
        "usage": "chat [list|get|load|rename ...]",
        "params": [
            ("list", "列出全部会话(id/名称、时间、连接、消息数)"),
            ("get <id|name>", "查看会话详情(含消息列表)"),
            ("load <id|name>", "加载会话并进入 chat 模式"),
            ("rename <旧名> <新名>", "重命名会话;旧名输入时 Tab 可补全选择"),
        ],
    },
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_shell.py tests/test_shell_lexer.py tests/test_help_data.py -q`
Expected: 全部 PASS

再跑全量:`uv run pytest -q`,Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/shell.py src/rp_agent/help_data.py tests/test_shell.py tests/test_shell_lexer.py tests/test_help_data.py
git commit -m "feat: chat 子命令系统(list/get/load/rename)+ 模式内 /rename"
```

---

### Task 4: rename tab 补全(prompt_toolkit completer)

**Files:**
- Modify: `src/rp_agent/shell.py`(ChatRenameCompleter、_read_line 加 completer)
- Test: `tests/test_shell_lexer.py`(或新建 `tests/test_shell_completer.py`)

**Interfaces:**
- Consumes: Task 2 `_chat_business("session_names")`;prompt_toolkit `Completer`/`Completion`/`WordCompleter`
- Produces: `ChatRenameCompleter`(shell.py 模块级类)

- [ ] **Step 1: 写失败测试**

新建 `tests/test_shell_completer.py`:

```python
from prompt_toolkit.document import Document

from rp_agent.shell import ChatRenameCompleter


def _complete(monkeypatch, tmp_path, text: str):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    from rp_agent.core.session import create_session, save_session

    s = create_session()
    s.name = "三体会话"
    save_session(s)
    doc = Document(text)
    return list(ChatRenameCompleter().get_completions(doc, None))


def test_rename_completer_suggests_after_prefix(monkeypatch, tmp_path):
    result = _complete(monkeypatch, tmp_path, "chat rename ")
    names = [c.text for c in result]
    assert "三体会话" in names


def test_rename_completer_suggests_partial_word(monkeypatch, tmp_path):
    result = _complete(monkeypatch, tmp_path, "chat rename 三体")
    names = [c.text for c in result]
    assert "三体会话" in names


def test_rename_completer_ignores_other_commands(monkeypatch, tmp_path):
    assert _complete(monkeypatch, tmp_path, "api list") == []
    assert _complete(monkeypatch, tmp_path, "chat get ") == []


def test_rename_completer_ignores_second_arg(monkeypatch, tmp_path):
    # chat rename <旧> <新> 已输入第二个参数 → 不再补全
    assert _complete(monkeypatch, tmp_path, "chat rename 三体会话 新") == []
```

- [ ] **Step 2: 跑测试确认失败**

Run: `uv run pytest tests/test_shell_completer.py -q`
Expected: FAIL — `ImportError: cannot import name 'ChatRenameCompleter'`

- [ ] **Step 3: 实现**

`src/rp_agent/shell.py`:

3a. 顶部 import 增加:

```python
from prompt_toolkit.completion import Completer, Completion, WordCompleter
```

3b. 新增 completer 类(放在 `ShellLexer` 之后、`_read_line` 之前):

```python
class ChatRenameCompleter(Completer):
    """chat rename 后的第一个参数:tab 补全会话名列表(zsh 式菜单)。"""

    def get_completions(self, document, complete_event):
        text = document.text
        parts = text.split()
        # 仅匹配 chat rename <第一个参数位置>
        if len(parts) < 2 or parts[0] != "chat" or parts[1] != "rename":
            return
        if len(parts) > 3 or (len(parts) == 3 and text.endswith(" ")):
            return  # 已进入第二参数位置,不再补全
        word_before = document.get_word_before_cursor(WORD=True)
        names = _chat_business("session_names")()
        if not names:
            return
        completer = WordCompleter(names, ignore_case=True)
        yield from completer.get_completions(document, complete_event)
```

3c. `_read_line` 的 `pt_prompt` 调用增加 `completer=ChatRenameCompleter()`:

```python
        return pt_prompt(
            fmt,
            lexer=ShellLexer(),
            style=SHELL_STYLE,
            history=_pt_history,
            completer=ChatRenameCompleter(),
        )
```

- [ ] **Step 4: 跑测试确认通过**

Run: `uv run pytest tests/test_shell_completer.py -q`
Expected: 全部 PASS

再跑全量:`uv run pytest -q`,Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/shell.py tests/test_shell_completer.py
git commit -m "feat: chat rename 参数 Tab 补全(prompt_toolkit completer,zsh 式选择)"
```

---

## 验证方式(全部完成后)

```bash
uv run pytest -v            # 全量测试通过
uv run rp-agent shell       # 手动:help 概览对齐;storage 报未知命令;config --help 显示字段
# chat rename 交互:输入 "chat rename " 按 Tab → 弹出会话列表 → 方向键选择 → 回车 → 输入新名
```

## 行为约定(实现时须保持)

- `chat` 无参进模式;`chat list/get/load/rename` 走子命令;`chat --help` 显示 chat 帮助
- `chat load <id|name>` 加载会话并切到 chat 模式(不新建会话)
- `storage` 命令已移除(未知命令);`storage.py` 底层保留
- `/rename <新名>` 仅在 chat 模式内可用(属 `_CHAT_COMMANDS`)
- tab 补全仅 tty 生效;非 tty 需完整输入参数
