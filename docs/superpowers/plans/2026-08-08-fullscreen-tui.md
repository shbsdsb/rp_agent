# 全屏 TUI 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 rp-agent 的交互界面从逐行 REPL 升级为全屏 TUI(状态栏 + 可滚动输出区 + 输入框),支持 `reload --tui/--cli` 运行中切换界面。

**Architecture:** 新增 `src/rp_agent/tui.py`(prompt_toolkit `Application` 三区布局);新增 `src/rp_agent/output.py` 统一输出回调(`emit`),shell.py / core/chat.py 的所有 `print` 改为 `emit`,TUI 下重定向到输出区;`run_shell` 外层加界面分发循环处理 `reload --tui/--cli` 切换;输出区滚动用 `_tail_offset`(距末尾偏移)切片渲染,绕开 prompt_toolkit 锚点机制(上次排查根因)。

**Tech Stack:** Python 3.14、prompt-toolkit 3.0.53(已验证 API:`FormattedTextControl.create_content` 可 override、`Window.allow_scroll_beyond_bottom`、`Keys.ScrollUp/ScrollDown`、`ANSI()` 转 FormattedText、`Buffer(accept_handler=...)`)、pytest

## Global Constraints

- 不新增第三方依赖(只用现有 prompt_toolkit/typer)
- 依赖/运行一律 UV:`uv run pytest -v`;禁止 pip/venv
- Python 版本固定 >= 3.14
- REPL 行为不得改变:现有 197 个测试必须全绿(输出默认仍走 stdout)
- `_tail_offset` 语义:0 = 贴底显示最新;正数 = 距末尾向上偏移行数
- 输出行上限 5000 行(超限丢弃最旧)
- 滚动逻辑必须抽纯函数并单测(`visible_slice`/`clamp_offset`)
- 模式切换(chat/rp/agent/exit 回 home)清空输出区;`reload --tui/--cli` 切换界面保留输出历史
- 默认界面为 TUI(`_ui_mode = "tui"`);`reload --tui` 已处于 TUI 时提示"已是 tui 界面"不重启
- 旧 `reload`(无参数)行为不变 = 热重载配置
- prompt_toolkit 无 `ansigray`,灰色用 `ansibrightblack`

---

### Task 1: 统一输出回调 `output.py` + print 替换

**Files:**
- Create: `src/rp_agent/output.py`
- Modify: `src/rp_agent/shell.py`(全部 `print(` → `emit(`;加 import)
- Modify: `src/rp_agent/core/chat.py`(全部 `print(` → `emit(`;加 import)
- Test: `tests/test_output.py`

**Interfaces:**
- Produces:
  - `output.emit(text: str) -> None` — 输出一行文本(默认落到 `print`)
  - `output.set_emit_target(fn: Callable[[str], None]) -> None`
  - `output.reset_emit_target() -> None` — 恢复默认 `print`
  - `output.is_tui() -> bool` — 当前目标是否非 `print`(供 spinner 降级)

- [ ] **Step 1: 写失败测试 `tests/test_output.py`**

```python
from rp_agent import output


def test_emit_default_goes_to_stdout(capsys):
    output.emit("你好")
    assert capsys.readouterr().out == "你好\n"


def test_set_emit_target_redirects(capsys):
    collected: list[str] = []
    output.set_emit_target(collected.append)
    try:
        output.emit("a")
        output.emit("b")
    finally:
        output.reset_emit_target()
    assert collected == ["a", "b"]
    assert capsys.readouterr().out == ""  # 未落 stdout


def test_is_tui_flips_with_target():
    assert output.is_tui() is False
    output.set_emit_target(lambda s: None)
    try:
        assert output.is_tui() is True
    finally:
        output.reset_emit_target()
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_output.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rp_agent.output'`

- [ ] **Step 3: 写 `src/rp_agent/output.py`**

```python
"""统一输出回调:REPL 下默认落 stdout,TUI 下由 set_emit_target 重定向到输出区。

所有交互输出(shell 命令结果/chat 消息/错误提示)都经 emit(),界面层不感知输出目标。
"""
from __future__ import annotations

from typing import Callable

_emit_target: Callable[[str], None] = print


def emit(text: str) -> None:
    """输出一行文本,目标由 set_emit_target 决定(默认 print)。"""
    _emit_target(text)


def set_emit_target(fn: Callable[[str], None]) -> None:
    """重定向输出目标(如 TUI 输出区追加函数)。"""
    global _emit_target
    _emit_target = fn


def reset_emit_target() -> None:
    """恢复默认 print 目标。"""
    global _emit_target
    _emit_target = print


def is_tui() -> bool:
    """当前输出目标是否非默认 print(供 spinner 等降级用)。"""
    return _emit_target is not print
```

- [ ] **Step 4: 替换 shell.py 与 core/chat.py 的 print**

在 `src/rp_agent/shell.py` 与 `src/rp_agent/core/chat.py` 顶部加入:

```python
from rp_agent.output import emit
```

然后逐文件把调用形态的 `print(` 替换为 `emit(`(只替换代码中的调用,不碰注释/字符串里的 "print" 字样):

```bash
# 先审查每一处 print( 是否都是调用形态
grep -n "print(" src/rp_agent/shell.py src/rp_agent/core/chat.py
```

审查后用 python 脚本做精确替换(只替换 `print(` 出现处,注释里带括号的 "print" 也一并审查):

```bash
uv run python - <<'EOF'
import re
for path in ["src/rp_agent/shell.py", "src/rp_agent/core/chat.py"]:
    src = open(path, encoding="utf-8").read()
    # 仅替换 `print(` 调用;chat.py 的 print(..., flush=True) 保留参数
    out = src.replace("print(", "emit(")
    # 还原纯打印的 print() 空调用 → emit("")
    out = out.replace("emit()", 'emit("")')
    open(path, "w", encoding="utf-8", newline="\n").write(out)
    print(path, "done")
EOF
```

注意:chat.py 的 `print(f"{label}…", flush=True)` 替换后为 `emit(f"{label}…", flush=True)` —— **必须手动改回** `emit(f"{label}…")`(emit 签名只有 text;flush 语义交给输出区刷帧)。

- [ ] **Step 5: 全量回归**

Run: `uv run pytest -q`
Expected: 197 passed(行为不变;新增 test_output 3 个)

- [ ] **Step 6: Commit**

```bash
git add src/rp_agent/output.py tests/test_output.py src/rp_agent/shell.py src/rp_agent/core/chat.py
git commit -m "feat: 统一输出回调 output.emit,替换 shell/chat 的 print"
```

---

### Task 2: 抽取公共命令执行函数 `handle_line`

**Files:**
- Modify: `src/rp_agent/shell.py`(`run_shell` 循环体抽为 `handle_line(line)`;新增 `_quit_request`)
- Test: `tests/test_shell.py`(新增 handle_line 测试)

**Interfaces:**
- Consumes: `parse_line`(现有)、`_COMMANDS`(现有)、`emit`(Task 1)
- Produces:
  - `handle_line(line: str) -> None` — 执行一行输入(与界面无关);模式切换写 `_mode_switch_request`;home 模式 exit 置 `_quit_request = True`
  - `_quit_request: bool` — 模块级退出信号(REPL 循环/TUI accept_handler 读取)

**说明:** 原 `run_shell` 循环体(791-861 行)中,`mode` 局部变量改为 `_current_mode` 模块级表达;所有模式变化写入 `_mode_switch_request`;`exit`(home 模式)置 `_quit_request=True` 而不是 return。

- [ ] **Step 1: 写失败测试(追加到 `tests/test_shell.py`)**

```python
def test_handle_line_switches_mode_and_quits(capsys):
    import rp_agent.shell as shell_mod

    handle_line("chat")
    # handle_line 只写切换请求,模式由 run_shell/TUI 消费循环应用
    assert shell_mod._mode_switch_request == "chat"
    # 非 home 模式 /exit 回 home
    handle_line("/exit")
    assert shell_mod._mode_switch_request == "home"
    # home 模式 exit 置退出信号
    shell_mod._mode_switch_request = None
    handle_line("exit")
    assert shell_mod._quit_request is True


def test_handle_line_unknown_command_emits(capsys):
    handle_line("foobar")
    assert "未知命令" in capsys.readouterr().out
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_shell.py -k handle_line -v`
Expected: FAIL — `NameError: name 'handle_line' is not defined`

- [ ] **Step 3: 抽取 handle_line**

在 `src/rp_agent/shell.py` 中新增(模块级状态区加 `_quit_request = False`,并预定义界面状态供后续任务使用):

```python
_quit_request = False
_ui_mode: Literal["tui", "cli"] = "tui"  # 默认全屏 TUI(Task 5 消费)
_ui_switch_request: Literal["tui", "cli"] | None = None  # 界面切换请求
```

```python
def handle_line(line: str) -> None:
    """执行一行输入(与界面无关):命令分派/模式切换/对话消息。

    REPL 与 TUI 共用:模式变化写 _mode_switch_request;home 模式 exit 置 _quit_request。
    """
    global _current_mode, _chat_session, _mode_switch_request, _quit_request
    cmd, args = parse_line(line)
    if not cmd:
        return
    if line.strip() not in _history:
        _history.append(line.strip())
    escaped = cmd.startswith("/")
    if escaped:
        cmd = cmd[1:]
    if not cmd:
        return
    mode = _current_mode
    if cmd in ("exit", "quit"):
        if escaped and mode != "home":
            _mode_switch_request = "home"
            return
        if mode == "home":
            emit("退出")
            _quit_request = True
            return
        emit(gray(_placeholder_msg(mode)))
        return
    if mode != "home" and not escaped:
        if mode == "chat":
            if _chat_session is None:
                _chat_session = _chat_business("new_session")()
            _chat_business("send_message")(_chat_session, line.strip())
        else:
            emit(gray(_placeholder_msg(mode)))
        return
    if args == ["--help"]:
        _print_command_help(cmd)
        return
    if cmd in _MODE_COMMANDS and (cmd != "chat" or not args):
        _mode_switch_request = _MODE_COMMANDS[cmd]
        if _mode_switch_request == "chat":
            _chat_session = _chat_business("new_session")()
        return
    if mode != "home" and cmd in _CHAT_COMMANDS:
        if cmd == "new":
            _chat_session = _chat_business("new_session")()
        elif cmd == "list":
            _chat_business("list_sessions")()
        elif cmd == "load":
            if args:
                _chat_load(args[0])
            else:
                emit("用法: /load <会话id|name>(用 /list 查看)")
        elif cmd == "rename":
            if args:
                _chat_business("rename_session")(_chat_session, args[0])
            else:
                emit("用法: /rename <新名称>")
        return
    entry = _COMMANDS.get(cmd)
    if entry is None:
        emit(f"未知命令: {cmd}(输入 help 查看可用命令)")
        return
    try:
        entry[1](args)
    except Exception:
        logger.exception("命令执行失败: %s", cmd)
        emit(f"命令执行出错: {cmd}(详情见日志)")
```

将 `run_shell` 循环体改为调用 `handle_line`(保留提示符输入/EOF 处理/模式应用):

```python
def run_shell(
    _input: Callable[[str], str] = _read_line, initial_mode: Mode = "home"
) -> None:
    """交互式主循环(逐行 REPL)。"""
    global _current_mode, _chat_session, _mode_switch_request, _quit_request
    _history.clear()
    _quit_request = False
    mode = initial_mode
    emit(_BANNER)
    while True:
        if _mode_switch_request is not None:
            mode = _mode_switch_request
            _mode_switch_request = None
        _current_mode = mode
        try:
            line = _input(_prompt_for_mode(mode))
        except (EOFError, KeyboardInterrupt):
            emit("退出")
            return
        handle_line(line)
        if _quit_request:
            return
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/test_shell.py -v`
Expected: PASS(新增 2 个 + 现有全部)

- [ ] **Step 5: Commit**

```bash
git add src/rp_agent/shell.py tests/test_shell.py
git commit -m "refactor: 抽取 handle_line 公共命令执行,REPL/TUI 共用"
```

---

### Task 3: 输出缓冲与滚动纯函数

**Files:**
- Create: `src/rp_agent/tui.py`(本轮只加缓冲与纯函数部分)
- Test: `tests/test_tui_scroll.py`

**Interfaces:**
- Produces:
  - `visible_slice(total: int, height: int, tail_offset: int) -> tuple[int, int]` — 返回可见行区间 `[start, end)`
  - `clamp_offset(total: int, height: int, offset: int) -> int` — 把 offset 限制在 `[0, max(0, total - height)]`

- [ ] **Step 1: 写失败测试 `tests/test_tui_scroll.py`**

```python
from rp_agent.tui import clamp_offset, visible_slice


def test_visible_slice_tail():
    # 贴底(offset=0):显示最后 height 行
    assert visible_slice(total=100, height=10, tail_offset=0) == (90, 100)


def test_visible_slice_offsets_up():
    assert visible_slice(total=100, height=10, tail_offset=5) == (85, 95)


def test_visible_slice_content_less_than_height():
    assert visible_slice(total=3, height=10, tail_offset=0) == (0, 3)


def test_visible_slice_offset_clamped_at_bottom():
    # 3 行内容,height=10,offset 最多 0 → 显示全部
    assert visible_slice(total=3, height=10, tail_offset=7) == (0, 3)


def test_clamp_offset_bounds():
    assert clamp_offset(total=100, height=10, offset=-5) == 0
    assert clamp_offset(total=100, height=10, offset=3) == 3
    assert clamp_offset(total=100, height=10, offset=999) == 90
    assert clamp_offset(total=3, height=10, offset=5) == 0  # 内容不足一屏 → 只能贴底
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_tui_scroll.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'rp_agent.tui'`

- [ ] **Step 3: 写 `src/rp_agent/tui.py`(缓冲 + 纯函数部分)**

```python
"""全屏 TUI:三区布局(状态栏/可滚动输出区/输入框)。

滚动用 _tail_offset(距末尾偏移行数,0=贴底)对输出行切片渲染,
完全绕开 prompt_toolkit 锚点(光标)滚动机制——锚点在可视区内移动时视图不跟随是历史 bug 根因。
"""
from __future__ import annotations

MAX_LINES = 5000

_output_lines: list = []  # list[FormattedText],TUI 会话期间输出历史(跨界面切换保留)
_tail_offset = 0  # 0 = 贴底显示最新;正数 = 向上回看 offset 行


def visible_slice(total: int, height: int, tail_offset: int) -> tuple[int, int]:
    """可见行区间 [start, end):height 可视高度,tail_offset 距末尾偏移。"""
    end = max(0, total - tail_offset)
    start = max(0, end - height)
    return start, end


def clamp_offset(total: int, height: int, offset: int) -> int:
    """把 tail_offset 限制在合法范围:最小 0,最大 total-height(内容不足一屏只能贴底)。"""
    return max(0, min(offset, max(0, total - height)))
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/test_tui_scroll.py -v`
Expected: PASS(5 个)

- [ ] **Step 5: Commit**

```bash
git add src/rp_agent/tui.py tests/test_tui_scroll.py
git commit -m "feat: tui 输出缓冲滚动纯函数 visible_slice/clamp_offset"
```

---

### Task 4: 全屏 Application 布局与接入 emit

**Files:**
- Modify: `src/rp_agent/tui.py`(补全布局/Application/输出区/输入框)
- Modify: `src/rp_agent/shell.py`(导出 `SHELL_STYLE` 供 tui 合并样式——已是模块级,无需改;`_read_line` 不变)
- Test: `tests/test_tui_scroll.py`(追加缓冲行为测试)

**Interfaces:**
- Consumes: `visible_slice`/`clamp_offset`(Task 3)、`emit`/`set_emit_target`/`reset_emit_target`/`is_tui`(Task 1)、`handle_line`/`_mode_switch_request`/`_quit_request`/`_current_mode`(Task 2)、`ShellLexer`/`ShellCompleter`/`SHELL_STYLE`/`_prompt_for_mode`(现有)
- Produces:
  - `run(initial_mode: Mode = "home") -> None` — 进入全屏 TUI 事件循环;退出(真正退出)时恢复 emit 目标
  - `_append(text: str) -> None` — emit 目标:模式变化清空输出区、按行追加、贴底自动跟随
  - `_output_lines` / `_tail_offset` — 模块级,跨界面切换保留

- [ ] **Step 1: 追加失败测试(缓冲行为,`tests/test_tui_scroll.py`)**

```python
import rp_agent.tui as tui
from rp_agent import output


def test_append_stores_lines_and_follows_tail(capsys):
    tui._output_lines.clear()
    tui._tail_offset = 0
    output.set_emit_target(tui._append)
    try:
        tui._append("第一行")
        tui._append("第二行\n第三行")  # 多行 splitlines
        assert len(tui._output_lines) == 3
        assert tui._tail_offset == 0  # 贴底时新行自动跟随
    finally:
        output.reset_emit_target()


def _fmt_text(fmt) -> str:
    """FormattedText → 纯文本(拼 style 元组的 text 段)。"""
    return "".join(seg[1] for seg in fmt)


def test_append_respects_max_lines():
    tui._output_lines.clear()
    tui._tail_offset = 0
    for i in range(tui.MAX_LINES + 10):
        tui._append(f"行{i}")
    assert len(tui._output_lines) == MAX_LINES
    assert _fmt_text(tui._output_lines[0]) == "行10"  # 丢弃最旧 10 行


def test_append_keeps_offset_when_scrolled_back():
    tui._output_lines.clear()
    tui._tail_offset = 3  # 用户回看中
    for i in range(5):
        tui._append(f"行{i}")
    assert tui._tail_offset == 3  # 回看时新行不打断
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_tui_scroll.py -v`
Expected: FAIL — `AttributeError: module 'rp_agent.tui' has no attribute '_append'`

- [ ] **Step 3: 实现缓冲 + 布局 + Application**

在 `src/rp_agent/tui.py` 追加:

```python
from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl
from prompt_toolkit.mouse_events import MouseEventType

from rp_agent import output
from rp_agent.shell import (
    SHELL_STYLE,
    ShellCompleter,
    ShellLexer,
    _current_mode,
    _mode_switch_request,
    _prompt_for_mode,
    _quit_request,
    handle_line,
)

_current_mode_snapshot: str = ""


def _append(text: str) -> None:
    """emit 目标:模式变化 → 清空;追加行;贴底自动跟随。"""
    global _tail_offset, _current_mode_snapshot
    mode = _current_mode
    if mode != _current_mode_snapshot:
        _output_lines.clear()
        _tail_offset = 0
        _current_mode_snapshot = mode
    for sub in str(text).splitlines():
        _output_lines.append(FormattedText(ANSI(sub)))
    del _output_lines[:-MAX_LINES]
    # 贴底(_tail_offset==0)时新行自动跟随;回看(_tail_offset>0)时偏移不变,不打断阅读
    _invalidate()


def _scroll_by(delta: int) -> None:
    """按 10 行步进滚动(输出区实际高度由渲染时计算,步进取固定值即可)。"""
    global _tail_offset
    _tail_offset = clamp_offset(len(_output_lines), 10, _tail_offset + delta)
    _invalidate()


def _invalidate() -> None:
    if _app is not None:
        _app.invalidate()


class OutputControl(FormattedTextControl):
    """可滚动输出区:create_content 时按 _tail_offset 切片,绕开锚点机制。"""

    def __init__(self) -> None:
        super().__init__(text="")
        self._height = 1

    def create_content(self, width: int, height: int | None):
        h = height or 1
        self._height = h
        start, end = visible_slice(len(_output_lines), h, _tail_offset)
        self.text = FormattedText(_output_lines[start:end])
        return super().create_content(width, height)

    def mouse_handler(self, mouse_event):
        if mouse_event.event_type == MouseEventType.SCROLL_UP:
            _scroll_by(3)
            return True
        if mouse_event.event_type == MouseEventType.SCROLL_DOWN:
            _scroll_by(-3)
            return True
        return NotImplemented


def _status_text() -> FormattedText:
    parts: list[tuple[str, str]] = [("class:status-mode", f"[{_current_mode}]")]
    import rp_agent.shell as shell_mod  # 惰性,避免循环 import
    s = shell_mod._chat_session
    if s is not None:
        parts.append(("class:status-dim", f" 会话 {s.name or s.id}"))
        if s.connection:
            parts.append(("class:status-dim", f" 连接 {s.connection}"))
    return FormattedText(parts)


def _accept(buff: Buffer) -> None:
    line = buff.text
    buff.reset()
    if not line.strip():
        return
    handle_line(line)
    if _quit_request:
        _app.exit()
        return
    if _ui_switch_request():
        _app.exit()
        return
    _invalidate()


_app: Application | None = None


def run(initial_mode: str = "home") -> None:
    """进入全屏 TUI 事件循环;真正退出后恢复 emit 目标。"""
    global _app, _tail_offset, _current_mode_snapshot, _output_lines
    import rp_agent.shell as shell_mod

    shell_mod._current_mode = initial_mode
    _current_mode_snapshot = initial_mode
    output.set_emit_target(_append)
    try:
        buff = Buffer(accept_handler=_accept, multiline=False)
        kb = KeyBindings()

        @kb.add("pageup")
        def _page_up(event):
            _scroll_by(10)

        @kb.add("pagedown")
        def _page_down(event):
            _scroll_by(-10)

        @kb.add("home")
        def _go_top(event):
            global _tail_offset
            _tail_offset = clamp_offset(len(_output_lines), 10, len(_output_lines))

        @kb.add("end")
        def _go_bottom(event):
            global _tail_offset
            _tail_offset = 0

        style = SHELL_STYLE
        output_win = Window(OutputControl(), wrap_lines=False, allow_scroll_beyond_bottom=True)
        layout = Layout(
            HSplit(
                [
                    Window(FormattedTextControl(_status_text), height=1, style="class:status"),
                    output_win,
                    Window(
                        FormattedTextControl(
                            "reload --tui/--cli 切换界面 | PageUp/PageDown/滚轮滚动 | exit 退出"
                        ),
                        height=1,
                        style="class:hint",
                    ),
                    VSplit(
                        [
                            Window(
                                FormattedTextControl(_prompt_for_mode(_current_mode)),
                                width=10,
                                dont_extend_width=True,
                                style="class:chat-prompt",
                            ),
                            Window(
                                BufferControl(
                                    buffer=buff,
                                    lexer=ShellLexer(),
                                    completer=ShellCompleter(),
                                ),
                                height=1,
                            ),
                        ]
                    ),
                ]
            )
        )
        _app = Application(
            layout=layout,
            style=style,
            full_screen=True,
            mouse_support=True,
            key_bindings=kb,
        )
        _app.run()
    finally:
        output.reset_emit_target()
        _app = None
```

`_ui_switch_request` 辅助(读 shell 模块状态):

```python
def _ui_switch_request() -> bool:
    import rp_agent.shell as shell_mod
    return shell_mod._ui_switch_request is not None
```

样式:在 `src/rp_agent/shell.py` 的 `SHELL_STYLE` 基础上补充(把 `SHELL_STYLE` 改为可合并的 dict,或直接在该 dict 里加):

```python
SHELL_STYLE = Style.from_dict(
    {
        "cmd": "ansiyellow bold",
        "param": "ansibrightcyan",
        "opt": "ansibrightblack",
        "chat-prompt": "#FFE066 bold",
        "status": "bg:#1a1a2e #e0e0e0",       # 状态栏:深底浅字
        "status-mode": "ansiyellow bold",
        "status-dim": "ansibrightblack",
        "hint": "ansibrightblack",
    }
)
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/test_tui_scroll.py -v`
Expected: PASS(缓冲 3 个新增 + 滚动 5 个)

- [ ] **Step 5: 冒烟验证 TUI 启动(非 tty 用注入模式,直接人工验证)**

Run: `uv run python -c "from rp_agent.tui import visible_slice, clamp_offset; print(visible_slice(100,10,0))"`
Expected: `(90, 100)`;完整 TUI 冒烟:`uv run rp-agent shell` 人工进入(滚动/补全/着色/`reload --cli`)。

- [ ] **Step 6: Commit**

```bash
git add src/rp_agent/tui.py src/rp_agent/shell.py tests/test_tui_scroll.py
git commit -m "feat: 全屏 TUI 三区布局与滚动输出区"
```

---

### Task 5: `reload --tui/--cli` 界面切换与分发循环

**Files:**
- Modify: `src/rp_agent/shell.py`(`_cmd_reload` 支持 `--tui/--cli`;新增 `_ui_mode`/`_ui_switch_request`;`run_shell` 外层分发循环)
- Test: `tests/test_shell.py`(追加切换/幂等测试)

**Interfaces:**
- Consumes: `tui.run`(Task 4)
- Produces:
  - `_ui_mode: Literal["tui", "cli"]` — 模块级,默认 `"tui"`
  - `_ui_switch_request: Literal["tui", "cli"] | None` — 界面切换请求(当前界面退出后由分发循环消费)

- [ ] **Step 1: 写失败测试(追加到 `tests/test_shell.py`)**

```python
def test_reload_ui_switch_and_idempotent(capsys):
    import rp_agent.shell as shell_mod

    # 默认 TUI;reload --tui 幂等
    shell_mod._ui_mode = "tui"
    shell_mod._ui_switch_request = None
    handle_line("reload --tui")
    assert shell_mod._ui_switch_request is None
    assert "已是 tui 界面" in capsys.readouterr().out

    # reload --cli 请求切换
    handle_line("reload --cli")
    assert shell_mod._ui_switch_request == "cli"

    # 已在 cli 时 reload --cli 幂等
    shell_mod._ui_mode = "cli"
    shell_mod._ui_switch_request = None
    handle_line("reload --cli")
    assert shell_mod._ui_switch_request is None
    assert "已是 cli 界面" in capsys.readouterr().out

    # reload 无参数仍是热重载配置
    handle_line("reload")
    assert "配置已重载" in capsys.readouterr().out


def test_dispatch_loop_switches_ui(monkeypatch, capsys):
    import rp_agent.shell as shell_mod

    calls: list[str] = []
    real_tui_run = None
    monkeypatch.setattr(shell_mod, "_ui_mode", "cli")
    # 模拟:第一次跑 REPL 时注入 reload --tui + exit,应切到 tui 后真正退出
    monkeypatch.setattr(
        "rp_agent.tui.run",
        lambda initial_mode: calls.append(f"tui:{initial_mode}"),
    )
    # 用注入输入:cli 模式跑 REPL,输入 reload --tui 后退出
    shell_mod.run_shell(_feed(["reload --tui", "exit"]))
    assert calls == ["tui:home"]  # 分发循环:cli → 切 tui → 跑 tui.run → tui 内 exit → break
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_shell.py -k "reload_ui or dispatch_loop" -v`
Expected: FAIL — `AttributeError: module 'rp_agent.shell' has no attribute '_ui_mode'`

- [ ] **Step 3: 实现切换状态与分发循环**

`_ui_mode`/`_ui_switch_request` 已在 Task 2 定义,此处不再重复。`_cmd_reload` 改为:

```python
def _cmd_reload(args: list[str]) -> None:
    if args in (["--tui"], ["--cli"]):
        global _ui_mode, _ui_switch_request
        target = args[0][2:]
        if _ui_mode == target:
            emit(f"已是 {target} 界面")
            return
        _ui_switch_request = target
        emit(f"切换到 {target} 界面…")
        return
    changed = reload_config()
    cfg = get_config()
    emit(f"配置已重载,发生变化: {changed},log_level={cfg.log_level}")
```

`run_shell` 改为界面分发循环(原 REPL 循环保留为内部函数 `_run_repl`):

```python
def run_shell(
    _input: Callable[[str], str] = _read_line, initial_mode: Mode = "home"
) -> None:
    """界面分发循环:TUI(默认)与旧 REPL 之间按 _ui_switch_request 切换。"""
    global _ui_mode, _ui_switch_request, _current_mode
    while True:
        _ui_switch_request = None
        _current_mode = initial_mode
        if _ui_mode == "tui":
            try:
                from rp_agent.tui import run as tui_run

                tui_run(initial_mode)
            except Exception:
                logger.exception("TUI 运行异常,回退 REPL")
                _run_repl(_input, initial_mode)
        else:
            _run_repl(_input, initial_mode)
        if _ui_switch_request is not None:
            _ui_mode = _ui_switch_request
            continue
        return


def _run_repl(
    _input: Callable[[str], str] = _read_line, initial_mode: Mode = "home"
) -> None:
    """逐行 REPL 循环(Task 2 改造后的原 run_shell 主体)。"""
    global _current_mode, _chat_session, _mode_switch_request, _quit_request
    _history.clear()
    _quit_request = False
    mode = initial_mode
    emit(_BANNER)
    while True:
        if _mode_switch_request is not None:
            mode = _mode_switch_request
            _mode_switch_request = None
        _current_mode = mode
        try:
            line = _input(_prompt_for_mode(mode))
        except (EOFError, KeyboardInterrupt):
            emit("退出")
            return
        handle_line(line)
        if _quit_request:
            return
```

- [ ] **Step 4: 运行测试**

Run: `uv run pytest tests/test_shell.py -v`
Expected: PASS(新增 2 个 + 现有全部);`dispatch_loop` 测试中 `_feed` 在 cli 模式跑 `reload --tui` 后,分发循环切到 tui 调用 monkeypatched `tui.run`(记录调用),随后 `break` 返回。

- [ ] **Step 5: 冒烟验证切换**

Run: `uv run rp-agent shell` — 默认进全屏 TUI;输入 `reload --cli` 切 REPL;再 `reload --tui` 切回;`exit` 退出。

- [ ] **Step 6: Commit**

```bash
git add src/rp_agent/shell.py tests/test_shell.py
git commit -m "feat: reload --tui/--cli 运行中切换界面 + 分发循环"
```

---

### Task 6: 收尾联动与全量回归

**Files:**
- Modify: `src/rp_agent/core/chat.py`(`_spinner` 在 TUI 下降级静默)
- Modify: `AGENTS.md`(入口/架构补 TUI 与 output)
- Test: 全量回归

- [ ] **Step 1: 写失败测试(`tests/test_chat.py` 追加)**

```python
def test_spinner_silent_in_tui(capsys, monkeypatch):
    from rp_agent import output
    from rp_agent.core import chat

    output.set_emit_target(lambda s: None)  # 模拟 TUI
    try:
        with chat._spinner():
            pass
    finally:
        output.reset_emit_target()
    # TUI 下 spinner 不打印任何内容
    assert capsys.readouterr().out == ""
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_chat.py -k spinner -v`
Expected: FAIL — spinner 仍打印占位内容(TUI 下未降级)

- [ ] **Step 3: 实现 spinner 降级**

在 `src/rp_agent/core/chat.py` 的 `_spinner` 上下文管理器开头加:

```python
@contextmanager
def _spinner():
    if output.is_tui():
        yield  # TUI 下静默:全屏渲染自有刷新,不打印占位
        return
    ...原有实现...
```

(确认 `from rp_agent.output import emit` 已在 chat.py,并补 `import rp_agent.output as output` 或 `from rp_agent import output`。)

- [ ] **Step 4: 模式切换清空验证(人工冒烟)**

Run: `uv run rp-agent shell` — TUI 下 `help` 看输出;输入 `chat` 进入 chat 模式,确认输出区清空且显示新会话信息;`/exit` 回 home。

- [ ] **Step 5: 全量回归**

Run: `uv run pytest -q`
Expected: 全部 PASS(原 197 + 新增,约 207+)

- [ ] **Step 6: 更新 AGENTS.md**

在 AGENTS.md 的 Architecture 与入口处补充:`src/rp_agent/tui.py`(全屏 TUI 三区布局,`_tail_offset` 滚动)、`src/rp_agent/output.py`(emit 统一输出回调)、`reload --tui/--cli` 界面切换;命令区补 `uv run rp-agent shell` 默认进全屏 TUI 的说明。

- [ ] **Step 7: Commit**

```bash
git add src/rp_agent/core/chat.py tests/test_chat.py AGENTS.md
git commit -m "feat: TUI 下 spinner 降级静默;更新 AGENTS.md"
```

---

## 验收清单(全部完成后)

- [ ] `uv run pytest -q` 全绿(原 197 + 新增)
- [ ] `uv run rp-agent shell` 默认进全屏 TUI;滚轮/PageUp/Down 回看;Tab 补全与着色正常
- [ ] `reload --cli` 切旧 REPL,`reload --tui` 切回;重复执行提示"已是 xx 界面"
- [ ] chat 模式输出区随模式切换清空;`reload` 切换界面后输出历史保留
- [ ] 全屏 TUI 渲染异常时回退逐行 REPL,不崩进程
