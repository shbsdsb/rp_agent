# Shell 颜色与 Help 增强实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 增强 shell 可读性:新增终端颜色工具(黄/蓝/灰/粗体,零依赖 ANSI)、帮助数据表单、help 概览着色与 `<命令> --help` 详细帮助(参考 winget 样式)。

**Architecture:** 新增 `term.py`(颜色工具,`_ENABLED` 模块级开关)与 `help_data.py`(HELP_ENTRIES 表单 + `find_entry`);`shell.py` 主循环在分发前统一处理 `args == ["--help"]` → `_print_command_help`;`_colorize_usage` 按 token 着色(命令黄/选项灰/参数蓝)。

**Tech Stack:** Python 3.14、标准库(os/sys/ctypes)、pytest。

## Global Constraints

- Python >= 3.14;测试一律 `uv run pytest`(Windows,不用 python3)
- 不新增依赖(ANSI 转义 + ctypes 启用 VT);`uv.lock` 不变
- 颜色规则(参考 winget):命令名**黄**、参数名(`<name>`/`list` 等)**蓝**、有效选项(`--help`/`-h` 等 `-` 前缀)**灰**
- 非 tty / `NO_COLOR` 环境输出纯文本(无 ANSI)
- 现有 50 项测试保持通过
- 工作分支 `feat/api-connection`(延续)

---

### Task 1: `term.py` + `help_data.py`

**Files:**
- Create: `src/rp_agent/term.py`
- Create: `src/rp_agent/help_data.py`
- Create: `tests/test_term.py`
- Create: `tests/test_help_data.py`

**Interfaces:**
- Consumes: 无(仅标准库)
- Produces:
  - `term.supports_color() -> bool`、`term.yellow/blue/gray/bold(text: str) -> str`、`term._ENABLED: bool`(可 monkeypatch)
  - `help_data.HELP_ENTRIES: list[dict[str, object]]`(每条含 command/aliases/desc/usage/params)
  - `help_data.find_entry(command: str) -> dict[str, object] | None`(按命令名或别名查找)

- [ ] **Step 1: 写失败测试 `tests/test_term.py` 与 `tests/test_help_data.py`**

`tests/test_term.py`:
```python
from rp_agent import term


def test_colors_wrap_when_enabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", True)
    assert term.yellow("x") == "\033[33mx\033[0m"
    assert term.blue("x") == "\033[34mx\033[0m"
    assert term.gray("x") == "\033[90mx\033[0m"
    assert term.bold("x") == "\033[1mx\033[0m"


def test_colors_passthrough_when_disabled(monkeypatch):
    monkeypatch.setattr("rp_agent.term._ENABLED", False)
    assert term.yellow("x") == "x"
    assert term.blue("x") == "x"
    assert term.gray("x") == "x"
    assert term.bold("x") == "x"
```

`tests/test_help_data.py`:
```python
from rp_agent.help_data import HELP_ENTRIES, find_entry


def test_entries_have_required_fields():
    for entry in HELP_ENTRIES:
        assert entry["command"]
        assert entry["desc"]
        assert entry["usage"]
        assert isinstance(entry["params"], list)


def test_command_names_unique():
    names = [e["command"] for e in HELP_ENTRIES]
    assert len(names) == len(set(names))


def test_aliases_unique_and_no_overlap():
    aliases = [a for e in HELP_ENTRIES for a in e["aliases"]]
    assert len(aliases) == len(set(aliases))  # 无重复别名
    names = {e["command"] for e in HELP_ENTRIES}
    assert not (set(aliases) & names)  # 别名不与命令名重叠


def test_find_entry_by_command_and_alias():
    assert find_entry("help") is not None
    assert find_entry("?") is not None
    assert find_entry("quit") is not None
    assert find_entry("nope") is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_term.py tests/test_help_data.py -v
```
Expected: FAIL(`ModuleNotFoundError: No module named 'rp_agent.term'`)

- [ ] **Step 3: 写实现文件**

`src/rp_agent/term.py`:
```python
"""终端颜色工具(ANSI,零依赖)。非 tty / NO_COLOR 时原样返回。"""
from __future__ import annotations

import os
import sys

_ANSI = {
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "gray": "\033[90m",
    "bold": "\033[1m",
}
_RESET = "\033[0m"


def supports_color() -> bool:
    """是否启用颜色:stdout 是 tty 且未设 NO_COLOR;Windows 启用 VT 模式。"""
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                # ENABLE_VIRTUAL_TERMINAL_PROCESSING
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        except (AttributeError, OSError):
            return False
    return True


_ENABLED = supports_color()


def yellow(text: str) -> str:
    return f"{_ANSI['yellow']}{text}{_RESET}" if _ENABLED else text


def blue(text: str) -> str:
    return f"{_ANSI['blue']}{text}{_RESET}" if _ENABLED else text


def gray(text: str) -> str:
    return f"{_ANSI['gray']}{text}{_RESET}" if _ENABLED else text


def bold(text: str) -> str:
    return f"{_ANSI['bold']}{text}{_RESET}" if _ENABLED else text
```

`src/rp_agent/help_data.py`:
```python
"""Shell 帮助数据表单(查询表单)。"""
from __future__ import annotations

HELP_ENTRIES: list[dict[str, object]] = [
    {
        "command": "help",
        "aliases": ["?"],
        "desc": "显示帮助(help | <命令> --help)",
        "usage": "help [命令]",
        "params": [("命令", "可选:查看指定命令的详细帮助")],
    },
    {
        "command": "config",
        "aliases": [],
        "desc": "显示当前配置",
        "usage": "config",
        "params": [],
    },
    {
        "command": "reload",
        "aliases": [],
        "desc": "热重载配置",
        "usage": "reload",
        "params": [],
    },
    {
        "command": "storage",
        "aliases": [],
        "desc": "列出 data 目录内容",
        "usage": "storage",
        "params": [],
    },
    {
        "command": "hello",
        "aliases": [],
        "desc": "冒烟命令",
        "usage": "hello",
        "params": [],
    },
    {
        "command": "history",
        "aliases": [],
        "desc": "显示输入历史",
        "usage": "history",
        "params": [],
    },
    {
        "command": "exit",
        "aliases": ["quit"],
        "desc": "退出 shell",
        "usage": "exit",
        "params": [],
    },
    {
        "command": "api",
        "aliases": [],
        "desc": "API 连接管理",
        "usage": "api <list|get|add|del|test> ...",
        "params": [
            ("list", "列出所有连接"),
            ("get <name>", "查看连接详情(密钥打码)"),
            ("add <name> <base_url> <model> [api_key]", "新增/覆盖连接"),
            ("del <name>", "删除连接"),
            ("test <name>", "真实调用验证连接"),
        ],
    },
]


def find_entry(command: str) -> dict[str, object] | None:
    """按命令名(含别名)查找帮助条目。"""
    for entry in HELP_ENTRIES:
        if command == entry["command"] or command in entry["aliases"]:
            return entry
    return None
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_term.py tests/test_help_data.py -v
```
Expected: 6 passed(term 2 + help_data 4)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/term.py src/rp_agent/help_data.py tests/test_term.py tests/test_help_data.py
git commit -m "feat: 终端颜色工具(term.py)+ 帮助数据表单(help_data.py)"
```

---

### Task 2: `shell.py` 集成(help 概览着色 + `<命令> --help`)

**Files:**
- Modify: `src/rp_agent/shell.py`
- Modify: `tests/test_shell.py`

**Interfaces:**
- Consumes: `term.yellow/blue/gray`(Task 1)、`HELP_ENTRIES`、`find_entry`(Task 1)
- Produces:
  - `_colorize_usage(usage: str) -> str`:token 着色(命令黄/`-`前缀灰/`<>`参数蓝)
  - `_print_command_help(command: str) -> None`:详细帮助(usage 着色 + 参数列表)
  - `_cmd_help(args)` 增强:无参 → 概览(命令黄,别名同行);`help <命令>` → 详情
  - `run_shell` 主循环:分发前 `args == ["--help"]` → `_print_command_help(cmd)`
  - `_cmd_api` 用法行用 `_colorize_usage`

- [ ] **Step 1: 追加失败测试 `tests/test_shell.py`**

```python
def test_shell_help_shows_alias_same_line(capsys):
    run_shell(_feed(["help", "exit"]))
    out = capsys.readouterr().out
    assert "exit/quit" in out
    assert "help/?" in out


def test_shell_command_dash_help(capsys):
    run_shell(_feed(["config --help", "exit"]))
    out = capsys.readouterr().out
    assert "用法" in out
    assert "config" in out


def test_shell_api_dash_help(capsys):
    run_shell(_feed(["api --help", "exit"]))
    out = capsys.readouterr().out
    assert "用法" in out
    assert "get <name>" in out


def test_shell_output_no_ansi_in_capsys(capsys):
    run_shell(_feed(["help", "exit"]))
    out = capsys.readouterr().out
    assert "\033" not in out  # capsys 非 tty,颜色关闭
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_shell.py -v
```
Expected: 新测试 FAIL(help 概览无别名同行 / config --help 无详细用法)

- [ ] **Step 3: 修改 `src/rp_agent/shell.py`**

在 import 区追加:
```python
from rp_agent.help_data import HELP_ENTRIES, find_entry
from rp_agent.term import blue, gray, yellow
```

替换 `_cmd_help` 与 `_cmd_history` 之间的内容,新增两个辅助函数:

```python
def _colorize_usage(usage: str) -> str:
    """usage 串按 token 着色:命令黄、-前缀选项灰、<>参数蓝。"""
    parts = []
    for tok in usage.split():
        if tok.startswith("-") and len(tok) > 1:
            parts.append(gray(tok))
        elif tok.startswith("<") and tok.endswith(">"):
            parts.append(blue(tok))
        else:
            parts.append(yellow(tok))
    return " ".join(parts)


def _print_command_help(command: str) -> None:
    entry = find_entry(command)
    if entry is None:
        print(f"未知命令: {command}(输入 help 查看可用命令)")
        return
    print(f"用法: {_colorize_usage(str(entry['usage']))}")
    for param, desc in entry["params"]:
        print(f"  {blue(param):<34} {desc}")


def _cmd_help(args: list[str]) -> None:
    if args:
        _print_command_help(args[0])
        return
    print("可用命令:")
    width = max(
        len(e["command"] + (("/" + "/".join(e["aliases"])) if e["aliases"] else ""))
        for e in HELP_ENTRIES
    )
    for e in HELP_ENTRIES:
        name = e["command"]
        if e["aliases"]:
            name += "/" + "/".join(e["aliases"])
        print(f"  {yellow(name):<{width + 4}} {e['desc']}")
    print("  输入 <命令> --help 查看详细用法")
```

在 `run_shell` 主循环分发处,`_COMMANDS.get(cmd)` 之后、调用 handler 之前插入 `--help` 统一处理:

```python
        entry = _COMMANDS.get(cmd)
        if entry is None:
            print(f"未知命令: {cmd}(输入 help 查看可用命令)")
            continue
        if args == ["--help"]:
            _print_command_help(cmd)
            continue
        try:
            entry[1](args)
        except Exception:
            logger.exception("命令执行失败: %s", cmd)
            print(f"命令执行出错: {cmd}(详情见日志)")
```

`_cmd_api` 的用法提示着色(替换各用法 print):

```python
    if not args:
        print(f"用法: {_colorize_usage('api <list|get|add|del|test> ...')}")
        return
```
其余分支的 `print("用法: api get <name>")` 等也改为 `print(f"用法: {_colorize_usage('api get <name>')}")`(get/del/test/add 五处)。

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_shell.py -v
```
Expected: 11 passed(原 7 + 新 4)

- [ ] **Step 5: 手动冒烟(颜色需真实终端,此处验证内容)**

```bash
printf "help\nexit\n" | uv run rp-agent shell
printf "config --help\napi --help\nexit\n" | uv run rp-agent shell
```
Expected: help 概览含 `exit/quit`、`help/?`;`config --help` 与 `api --help` 输出详细用法。

- [ ] **Step 6: 提交**

```bash
git add src/rp_agent/shell.py tests/test_shell.py
git commit -m "feat: shell help 增强(概览着色/别名同行/<命令> --help 详细帮助)"
```

---

### Task 3: 全量验证与收尾

**Files:**
- Modify: `README.md`(补充 `<命令> --help` 说明)

**Interfaces:**
- Consumes: Task 1-2 产物
- Produces: 全绿测试套件 + 完整 git 历史

- [ ] **Step 1: 运行全量测试**

```bash
uv run pytest -v
```
Expected: 60 passed(50 原有 + 2 term + 4 help_data + 4 shell)

- [ ] **Step 2: 更新 README.md(在"交互式 Shell"章节内追加一行)**

```markdown
输入 `<命令> --help`(如 `config --help`)查看该命令详细用法与参数。
```

- [ ] **Step 3: 确认工作树整洁并提交收尾**

```bash
git status --short
git add -A
git commit -m "chore: shell 颜色与 help 增强完成(README 更新)"
git log --oneline
```
Expected: `git log --oneline` 显示连续提交历史。

---

## 验收清单(对照 spec)

- [ ] `term.yellow/blue/gray/bold` ANSI 包裹;`_ENABLED` 关闭时原样返回 → spec §3.1
- [ ] `HELP_ENTRIES` 覆盖全部命令含 aliases/usage/params;`find_entry` 按名或别名查找 → spec §3.2
- [ ] help 概览:命令黄、别名同行(`exit/quit`、`help/?`)→ spec §3.3、§3.4
- [ ] `<命令> --help` 详细用法;`_colorize_usage` 命令黄/选项灰/参数蓝 → spec §3.3、§3.4
- [ ] capsys 非 tty 输出无 ANSI 转义 → spec §3.4、§5
- [ ] 现有 50 项测试保持通过,总计 60 passed → spec §7
