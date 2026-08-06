# Shell 全范围 Tab 自动补全 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `src/rp_agent/shell.py` 实现单一 `ShellCompleter`,为 shell 提供命令名/蓝色子命令/灰色选项/连接名/会话名的 dropdown Tab 补全,并删除旧 `ChatSessionCompleter`。

**Architecture:** 一个自定义 `Completer` 按"正在输入词的 0-based 位置"分派:位置 0 → 命令名(含 `/` 变体);位置 1 → `_COMMAND_ARGS` 蓝色子命令;位置 ≥2 → 选项(`-` 开头走 `_VALID_OPTIONS`)或第一个位置参数(`_POSITIONAL` 分发表 → 连接名/会话名,运行时读取)。候选数据源与 `ShellLexer` 完全同源("着色的词 = 可补全的词")。

**Tech Stack:** Python 3.14、UV、prompt_toolkit(Completer/WordCompleter/Document)、pytest。

## Global Constraints

- 只用 UV(`uv run pytest -v` 跑测试,`uv run rp-agent shell` 冒烟);Python >= 3.14
- 交互式 REPL 输入必须用 prompt_toolkit(已是);不新增任何依赖(prompt_toolkit 已具备)
- 数据读写统一走 `storage.py`(连接经 `rp_agent.api.store`,会话经 `rp_agent.core.session`)
- 分支 `feat/shell-autocomplete` 上小步提交;每步提交前只 add 本步涉及文件
- `ShellLexer` 与 `_COMMAND_ARGS`/`_VALID_OPTIONS`/`_KNOWN_COMMANDS` 的定义**不得改动**
- API 密钥脱敏、日志标准库 logging 等既有约定不涉及
- Windows:脚本保持 ASCII;本计划命令无路径尾反斜杠问题

---
**注意:** 三个任务都在 `src/rp_agent/shell.py` 中演进同一个 `ShellCompleter` 类:Task 1 定义静态部分,Task 2 扩成完整类(直接替换 Task 1 的类定义),Task 3 接线并删除旧类。测试 helper 在 Task 1 建立,Task 2 增加连接 fixture,Task 3 重写为最终版。

### Task 1: `ShellCompleter` 静态补全(命令名 + 蓝色子命令)

**Files:**
- Modify: `src/rp_agent/shell.py`(新增 `_COMMAND_NAMES` 常量与 `ShellCompleter` 类,插入到 `ChatSessionCompleter` 类之前)
- Test: `tests/test_shell_completer.py`(改写 helper 与用例,先删旧 `ChatSessionCompleter` 引用)

**Interfaces:**
- Consumes: `_KNOWN_COMMANDS`、`_COMMAND_ARGS`(shell.py 既有)、`WordCompleter`/`Completer`(prompt_toolkit 既有)
- Produces: `_COMMAND_NAMES: set[str]`(含 `/` 变体)、`ShellCompleter.get_completions(document, complete_event)` —— 后续任务沿用;Task 3 在 `_read_line` 使用 `ShellCompleter()`

- [ ] **Step 1: 重写测试 helper 并写失败测试(静态部分)**

把 `tests/test_shell_completer.py` 整体替换为:

```python
from prompt_toolkit.document import Document

from rp_agent.shell import ShellCompleter


def _complete(monkeypatch, tmp_path, text: str):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    doc = Document(text)
    return list(ShellCompleter().get_completions(doc, None))


def _names(result):
    return [c.text for c in result]


def test_command_name_completes_after_prefix():
    assert "api" in _names(_complete(None, None, "a"))
    assert "agent" in _names(_complete(None, None, "a"))


def test_command_name_completes_empty_line():
    names = _names(_complete(None, None, ""))
    assert "api" in names and "help" in names


def test_slash_command_completes():
    assert "/load" in _names(_complete(None, None, "/l"))
    assert "/exit" in _names(_complete(None, None, "/e"))


def test_subcommand_completes_after_prefix():
    assert "list" in _names(_complete(None, None, "api li"))
    assert "modify" in _names(_complete(None, None, "api m"))


def test_subcommand_completes_all_after_space():
    names = _names(_complete(None, None, "api "))
    for sub in ("list", "get", "add", "del", "test", "pull", "sync", "modify", "use", "set"):
        assert sub in names


def test_unknown_command_offers_nothing():
    assert _complete(None, None, "foobar ") == []
```

**注:** helper 里 `monkeypatch`/`tmp_path` 先传给 `_complete` 但静态用例用不到;`_complete(None, None, ...)` 直接传 None。若 pytest 报 fixture 名冲突,把静态用例的调用改为 `_complete("x", "y", text)` 亦可 —— 保证参数个数一致即可。

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_shell_completer.py -v`
Expected: FAIL —— `ImportError: cannot import name 'ShellCompleter' from 'rp_agent.shell'`

- [ ] **Step 3: 实现 `ShellCompleter`(静态部分)**

在 `src/rp_agent/shell.py` 的 `ChatSessionCompleter` 类**之前**插入:

```python
# 命令名补全候选:已知命令 + / 转义变体(模式内 /load、/exit 等)
_COMMAND_NAMES: set[str] = _KNOWN_COMMANDS | {f"/{c}" for c in _KNOWN_COMMANDS}


class ShellCompleter(Completer):
    """全范围 Tab 补全(dropdown):命令名/蓝色子命令/灰色选项/连接名/会话名。

    与 ShellLexer 共用 _KNOWN_COMMANDS/_COMMAND_ARGS/_VALID_OPTIONS 数据源,
    保证"着色的词 = 可补全的词"。按正在输入词的 0-based 位置分派:
    0=命令名,1=蓝色子命令,2=第一位置参数(选项在词以 - 开头时优先)。
    """

    def get_completions(self, document, complete_event):
        text = document.text
        if not text.strip():
            yield from self._words(_COMMAND_NAMES, document, complete_event)
            return
        parts = text.split()
        # 尾空格说明上一词已完成、正在输入新词
        position = len(parts) if text.endswith(" ") else len(parts) - 1
        if position == 0:
            yield from self._words(_COMMAND_NAMES, document, complete_event)
            return
        cmd = parts[0].lstrip("/")
        if position == 1:
            subs = _COMMAND_ARGS.get(cmd, set())
            if subs:
                yield from self._words(subs, document, complete_event)
            return
        # 位置参数/选项在 Task 2 实现;当前只做静态部分
        return

    @staticmethod
    def _words(words, document, complete_event):
        if not words:
            return
        completer = WordCompleter(sorted(words), ignore_case=True)
        yield from completer.get_completions(document, complete_event)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_shell_completer.py -v`
Expected: PASS(6 个新测试全绿)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/shell.py tests/test_shell_completer.py
git commit -m "feat: ShellCompleter 静态补全(命令名+蓝色子命令)"
```

---

### Task 2: `ShellCompleter` 选项与位置参数(连接名/会话名)

**Files:**
- Modify: `src/rp_agent/shell.py`(把 Task 1 的 `ShellCompleter` 类替换为完整版:加 `_POSITIONAL`、选项分支、动态读取)
- Test: `tests/test_shell_completer.py`(helper 增加连接 fixture,新增动态用例)

**Interfaces:**
- Consumes: `_VALID_OPTIONS`(shell.py 既有)、`list_connections`(已有 import)、`_chat_business("session_names")`(既有)、`ApiConnection`/`save_connection`(测试 fixture 用)
- Produces: `ShellCompleter._POSITIONAL: dict[tuple[str, str], str]`、动态候选逻辑(异常降级:动态读取失败 → 跳过,静态照常)

- [ ] **Step 1: 写失败测试(选项/连接名/会话名/第二参)**

把 `tests/test_shell_completer.py` 整体替换为:

```python
from prompt_toolkit.document import Document

from rp_agent.api.models import ApiConnection
from rp_agent.api.store import save_connection
from rp_agent.core.session import create_session, save_session
from rp_agent.shell import ShellCompleter


def _complete(monkeypatch, tmp_path, text: str):
    monkeypatch.setattr("rp_agent.storage.DATA_DIR", tmp_path)
    s = create_session()
    s.name = "三体会话"
    save_session(s)
    save_connection(
        ApiConnection(
            name="deepseek",
            base_url="https://api.deepseek.com",
            api_key="sk-test",
            model="deepseek-chat",
        )
    )
    doc = Document(text)
    return list(ShellCompleter().get_completions(doc, None))


def _names(result):
    return [c.text for c in result]


# --- 静态:命令名 / 子命令(沿用 Task 1) ---

def test_command_name_completes_after_prefix(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "a"))
    assert "api" in names and "agent" in names


def test_command_name_completes_empty_line(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, ""))
    assert "api" in names and "help" in names


def test_slash_command_completes(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "/l"))
    assert "/load" in names


def test_subcommand_completes_after_prefix(monkeypatch, tmp_path):
    assert "list" in _names(_complete(monkeypatch, tmp_path, "api li"))


def test_unknown_command_offers_nothing(monkeypatch, tmp_path):
    assert _complete(monkeypatch, tmp_path, "foobar ") == []


# --- 选项 ---

def test_option_completes_after_dash_prefix(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "api add --n"))
    assert "--name" in names


def test_short_option_completes(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "api del -"))
    assert "-f" in names and "-v" in names


def test_option_does_not_match_unknown(monkeypatch, tmp_path):
    assert _complete(monkeypatch, tmp_path, "api add --wat") == []


# --- 位置参数:连接名 / 会话名 ---

def test_connection_name_completes(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "api get "))
    assert "deepseek" in names


def test_connection_name_partial(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "api test deep"))
    assert "deepseek" in names


def test_session_name_completes(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "chat get "))
    assert "三体会话" in names


def test_slash_load_completes_session(monkeypatch, tmp_path):
    names = _names(_complete(monkeypatch, tmp_path, "/load 三体"))
    assert "三体会话" in names


def test_second_arg_not_completed(monkeypatch, tmp_path):
    # chat rename 第二参(新名)不补全
    assert _complete(monkeypatch, tmp_path, "chat rename 三体会话 新") == []
    assert _complete(monkeypatch, tmp_path, "api get deepseek ") == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_shell_completer.py -v`
Expected: FAIL —— 选项/连接名/会话名用例拿不到候选(静态实现返回空)

- [ ] **Step 3: 替换 `ShellCompleter` 为完整版**

把 Task 1 中的 `ShellCompleter` 类整体替换为:

```python
class ShellCompleter(Completer):
    """全范围 Tab 补全(dropdown):命令名/蓝色子命令/灰色选项/连接名/会话名。

    与 ShellLexer 共用 _KNOWN_COMMANDS/_COMMAND_ARGS/_VALID_OPTIONS 数据源,
    保证"着色的词 = 可补全的词"。按正在输入词的 0-based 位置分派:
    0=命令名,1=蓝色子命令,2=第一位置参数(词以 - 开头时优先补选项)。
    """

    # (命令, 子命令) → 第一个位置参数类型;未列出者不补位置参数
    _POSITIONAL: dict[tuple[str, str], str] = {
        ("api", "get"): "connection",
        ("api", "del"): "connection",
        ("api", "test"): "connection",
        ("api", "pull"): "connection",
        ("api", "sync"): "connection",
        ("api", "modify"): "connection",
        ("api", "use"): "connection",
        ("api", "set"): "connection",
        ("chat", "get"): "session",
        ("chat", "load"): "session",
        ("chat", "rename"): "session",
    }

    def get_completions(self, document, complete_event):
        text = document.text
        if not text.strip():
            yield from self._words(_COMMAND_NAMES, document, complete_event)
            return
        parts = text.split()
        # 尾空格说明上一词已完成、正在输入新词
        position = len(parts) if text.endswith(" ") else len(parts) - 1
        if position == 0:
            yield from self._words(_COMMAND_NAMES, document, complete_event)
            return
        first = parts[0]
        if first == "/load" and position == 1:
            yield from self._sessions(document, complete_event)
            return
        cmd = first.lstrip("/")
        if position == 1:
            subs = _COMMAND_ARGS.get(cmd, set())
            if subs:
                yield from self._words(subs, document, complete_event)
            return
        if position != 2:
            return  # 只补第一个位置参数(chat rename 第二参等不补)
        current = parts[-1]
        if current.startswith("-"):
            yield from self._words(_VALID_OPTIONS, document, complete_event)
            return
        ptype = self._POSITIONAL.get((cmd, parts[1]))
        if ptype == "connection":
            try:
                names = list_connections()
            except Exception:
                return
            yield from self._words(names, document, complete_event)
        elif ptype == "session":
            yield from self._sessions(document, complete_event)

    def _sessions(self, document, complete_event):
        try:
            names = _chat_business("session_names")() or []
        except Exception:
            return
        yield from self._words(names, document, complete_event)

    @staticmethod
    def _words(words, document, complete_event):
        if not words:
            return
        completer = WordCompleter(sorted(words), ignore_case=True)
        yield from completer.get_completions(document, complete_event)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_shell_completer.py -v`
Expected: PASS(静态 + 动态共 13 个用例全绿)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/shell.py tests/test_shell_completer.py
git commit -m "feat: ShellCompleter 选项与连接名/会话名补全"
```

---

### Task 3: 接线 `_read_line`、删除 `ChatSessionCompleter`、回归

**Files:**
- Modify: `src/rp_agent/shell.py:677-684`(`_read_line` 的 `completer=` 切换)、删除 `ChatSessionCompleter` 类(`src/rp_agent/shell.py:639-664`)
- Test: `tests/test_shell_completer.py`(已是最终版,无需改)

**Interfaces:**
- Consumes: Task 2 的 `ShellCompleter`(完整版)
- Produces: 运行时生效的 dropdown 补全;不再有 `ChatSessionCompleter` 符号

- [ ] **Step 1: 改 `_read_line` 使用 `ShellCompleter`**

`src/rp_agent/shell.py` 的 `_read_line` 中:

```python
            completer=ChatSessionCompleter(),
```

改为:

```python
            completer=ShellCompleter(),
```

- [ ] **Step 2: 删除 `ChatSessionCompleter` 类**

删除 `src/rp_agent/shell.py` 中整个 `ChatSessionCompleter` 类(含类 docstring 与 `_CMD_WORDS`、`get_completions` 方法,从 `class ChatSessionCompleter(Completer):` 到该类结束的 `yield from completer.get_completions(document, complete_event)` 行)。删除后确认模块中不再有 `ChatSessionCompleter` 引用:

Run: `grep -n "ChatSessionCompleter" src/rp_agent/shell.py`
Expected: 无输出(已全部移除)

- [ ] **Step 3: 跑补全测试确认通过**

Run: `uv run pytest tests/test_shell_completer.py -v`
Expected: PASS(13 个用例)

- [ ] **Step 4: 全量回归 + Lexer 不受影响**

Run: `uv run pytest -v`
Expected: PASS(全部测试,含 `tests/test_shell_lexer.py` 的着色用例)

- [ ] **Step 5: 冒烟验证(dropdown 交互)**

Run: `uv run rp-agent shell`
Expected: 进入 shell 后手动验证——输入 `a` 按 Tab 弹出命令候选(api/agent…);输入 `api ` 按 Tab 弹出蓝色子命令候选;输入 `api get ` 按 Tab 弹出已保存连接名;输入 `api add --` 按 Tab 弹出选项;方向键选择、回车确认。Ctrl+C 退出。
(若本地无已保存连接,`api get ` 后无候选属正常;可用 `api add --name demo --url https://x --key k` 造一个再试)

- [ ] **Step 6: 提交**

```bash
git add src/rp_agent/shell.py
git commit -m "feat: shell 接入 ShellCompleter,移除 ChatSessionCompleter"
```
