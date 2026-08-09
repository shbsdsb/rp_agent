# TUI 分区边框 + chat user 消息交替显示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** TUI 输出区显示 `user>`/`assistant>` 交替消息,并用 Unicode 圆角边框包裹全部四个分区。

**Architecture:** 功能 A 在 `core/chat.py` 的 `send_message` 内以 `output.is_tui()` 门控 emit `user>` 前缀行(CLI 保持终端回显零变化);功能 B 在 `tui.py` 新增 `framed()` 四边框容器(顶/底 = HSplit 角+char 填充+角,左右 = VSplit 空内容 Window char='│' 填充整列),四区全部包裹,`SHELL_STYLE` 加 `border` 样式。

**Tech Stack:** Python 3.14、prompt_toolkit(HSplit/VSplit/Window/FormattedTextControl)、pytest、uv

## Global Constraints

- Python >= 3.14,包管理/运行一律用 uv(`uv run`/`uv add`/`uv sync`),锁文件 uv.lock 提交
- 交互输入必须用 prompt_toolkit;prompt_toolkit 无 `ansigray`,灰色用 `ansibrightblack`
- 日志只用标准库 logging;依赖新增前必须 ask 确认(本计划不新增依赖)
- 分支:`feat/tui-borders-chat-display`;TDD(先写失败测试再实现);小步提交
- 测试命令:`uv run pytest -q`(现 231 个,完成后 235 个)

---

### Task 1: user 消息 TUI 门控 emit(功能 A)

**Files:**
- Modify: `src/rp_agent/core/chat.py`(新增 `USER_PREFIX` 常量;`send_message` 内加 TUI 门控 emit)
- Test: `tests/test_chat.py`(追加 2 个测试)

**Interfaces:**
- Consumes: `output.is_tui()`(src/rp_agent/output.py:29-31,`_emit_target is not print`)、`rgb(prefix, r, g, b)`(term.py)、`emit(text)`(output.py)
- Produces: 模块常量 `USER_PREFIX = "user> "`;`send_message` 在 TUI 下先 emit `user> <text>`(暖黄 rgb 255,224,102)再阻塞调 `chat()`

- [ ] **Step 1: 写失败测试**

在 `tests/test_chat.py` 末尾追加:

```python
def test_send_message_tui_emits_user_prefix(monkeypatch, tmp_path):
    """TUI 下 user 消息 emit 到输出区,先于 assistant(交替显示)。"""
    _setup(monkeypatch, tmp_path)
    collected: list[str] = []
    from rp_agent import output

    output.set_emit_target(collected.append)  # 模拟 TUI(emit 目标非默认 print)
    try:
        monkeypatch.setattr(
            "rp_agent.core.chat.chat",
            lambda conn, messages, **kw: "你好呀!",
        )
        s = create_session(connection="demo")
        save_session(s)
        send_message(s, "你好")
    finally:
        output.reset_emit_target()
    assert collected[0].startswith("user> 你好")
    assert "assistant> " in collected[-1]


def test_send_message_cli_no_user_emit(monkeypatch, tmp_path, capsys):
    """CLI(非 TUI)不 emit user 消息:依赖终端回显,避免重复。"""
    _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        "rp_agent.core.chat.chat",
        lambda conn, messages, **kw: "ok",
    )
    s = create_session(connection="demo")
    save_session(s)
    send_message(s, "你好")
    out = capsys.readouterr().out
    assert "user> " not in out
    assert "assistant> " in out
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_chat.py::test_send_message_tui_emits_user_prefix tests/test_chat.py::test_send_message_cli_no_user_emit -v`
Expected: FAIL(`user> ` 未输出 / `collected[0]` 是 assistant 行)

- [ ] **Step 3: 最小实现**

`src/rp_agent/core/chat.py`:

1) 第 22 行 `ASSISTANT_PREFIX` 常量旁新增:

```python
# user> 前缀色:暖黄(与输入前缀 chat> 的 #FFE066 同色系;assistant 用 #66AAFF 区分)
USER_PREFIX = "user> "
```

2) `send_message` 中,`session_store.save_session(s)`(现第 74 行)之后、`messages: list[dict] = []`(现第 75 行)之前插入:

```python
if output.is_tui():
    emit(f"{rgb(USER_PREFIX, 255, 224, 102)}{text}")
```

(`rgb` 已从 `rp_agent.term` 导入:`from rp_agent.term import rgb` 在文件顶部。)

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_chat.py -q`
Expected: PASS(含既有 8 个 chat 测试)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/core/chat.py tests/test_chat.py
git commit -m "feat: TUI 下 send_message emit user> 前缀(与 assistant> 交替显示)"
```

---

### Task 2: 分区边缘线包裹(功能 B)

**Files:**
- Modify: `src/rp_agent/tui.py`(新增 `framed()`;布局四区全部包裹)
- Modify: `src/rp_agent/shell/completion.py`(`SHELL_STYLE` 加 `border` 样式)
- Test: `tests/test_tui_scroll.py`(追加 2 个测试)

**Interfaces:**
- Consumes: prompt_toolkit `HSplit/VSplit/Window/FormattedTextControl`(已 import)、`SHELL_STYLE`(shell/completion.py)
- Produces: `framed(inner) -> HSplit`(四边框包裹容器);`class:border` 样式(灰 `ansibrightblack`);布局四区全部经 `framed()` 包裹

- [ ] **Step 1: 写失败测试**

在 `tests/test_tui_scroll.py` 末尾追加(顶部补 import):

```python
from prompt_toolkit.layout.containers import HSplit, VSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl

from rp_agent.tui import framed


def test_framed_builds_border_structure():
    """framed 返回 HSplit(顶线/内容/底线),内容左右包竖线列。"""
    inner = Window(FormattedTextControl("x"))
    box = framed(inner)
    assert isinstance(box, HSplit)
    assert len(box.children) == 3
    mid = box.children[1]
    assert isinstance(mid, VSplit)
    assert len(mid.children) == 3
    assert mid.children[1] is inner


def test_shell_style_has_border_rule():
    from rp_agent.shell import SHELL_STYLE

    rules = dict(SHELL_STYLE.style_rules)
    assert "border" in rules
```

- [ ] **Step 2: 运行测试确认失败**

Run: `uv run pytest tests/test_tui_scroll.py::test_framed_builds_border_structure tests/test_tui_scroll.py::test_shell_style_has_border_rule -v`
Expected: FAIL(`ImportError: cannot import name 'framed' from 'rp_agent.tui'` / `KeyError: 'border'`)

- [ ] **Step 3: 实现 framed + 样式 + 布局**

3a. `src/rp_agent/tui.py`,在 `top_offset` 函数之后新增:

```python
def framed(inner) -> HSplit:
    """四边框包裹 inner:Unicode 圆角(╭─╮│╰╯),宽度/高度自适应。

    顶/底边框行 = HSplit(左角, char='─' 填充, 右角):角字符固定在两端,
    中间由 Window char 填充横线;左右竖线 = VSplit 中空内容 Window
    char='│' 填充整列(高度由 inner 决定)。
    """
    def _line(left: str, right: str) -> HSplit:
        return HSplit(
            [
                Window(
                    FormattedTextControl(left),
                    width=1,
                    height=1,
                    dont_extend_width=True,
                    style="class:border",
                ),
                Window(
                    FormattedTextControl(""),
                    char="─",
                    height=1,
                    style="class:border",
                ),
                Window(
                    FormattedTextControl(right),
                    width=1,
                    height=1,
                    dont_extend_width=True,
                    style="class:border",
                ),
            ]
        )

    return HSplit(
        [
            _line("╭", "╮"),
            VSplit(
                [
                    Window(
                        FormattedTextControl(""),
                        char="│",
                        width=1,
                        dont_extend_width=True,
                        style="class:border",
                    ),
                    inner,
                    Window(
                        FormattedTextControl(""),
                        char="│",
                        width=1,
                        dont_extend_width=True,
                        style="class:border",
                    ),
                ]
            ),
            _line("╰", "╯"),
        ]
    )
```

3b. `src/rp_agent/tui.py`,`run()` 内 layout 构建(现第 215-248 行)改为四区全部包裹:

```python
        layout = Layout(
            HSplit(
                [
                    framed(
                        Window(
                            FormattedTextControl(_status_text),
                            height=1,
                            style="class:status",
                        )
                    ),
                    framed(output_win),
                    framed(
                        VSplit(
                            [
                                Window(
                                    FormattedTextControl(
                                        lambda: _prompt_for_mode(shell_mod._current_mode)
                                    ),
                                    width=10,
                                    dont_extend_width=True,
                                    style="class:chat-prompt",
                                ),
                                Window(
                                    BufferControl(buffer=buff, lexer=ShellLexer()),
                                    height=1,
                                ),
                            ]
                        )
                    ),
                    framed(
                        Window(
                            FormattedTextControl(
                                "reload --tui/--cli 切换界面 | PageUp/PageDown/滚轮滚动 | exit 退出"
                            ),
                            height=1,
                            style="class:hint",
                        )
                    ),
                ]
            )
        )
```

3c. `src/rp_agent/shell/completion.py`,`SHELL_STYLE` 字典(`"hint": "ansibrightblack",` 行)后追加:

```python
        "border": "ansibrightblack",  # 边框线:灰色(prompt_toolkit 无 ansigray,用亮黑)
```

- [ ] **Step 4: 运行测试确认通过**

Run: `uv run pytest tests/test_tui_scroll.py -q`
Expected: PASS(含既有滚动纯函数测试)

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/tui.py src/rp_agent/shell/completion.py tests/test_tui_scroll.py
git commit -m "feat: TUI 四区用 Unicode 圆角边框包裹(framed 容器)"
```

---

### Task 3: 全量回归与冒烟验证

**Files:**
- 无代码改动;验证 + 文档标注

**Interfaces:**
- 验证 Task 1/2 的组合正确性

- [ ] **Step 1: 全量测试**

Run: `uv run pytest -q`
Expected: 235 passed(231 既有 + 4 新增)

- [ ] **Step 2: 非 tty 冒烟(回退路径不崩)**

Run: `printf 'help\nexit\n' | uv run rp-agent shell`
Expected: TUI 因无控制台回退 REPL,help/exit 正常输出,无 traceback

- [ ] **Step 3: 编译与导入检查**

Run: `uv run python -m compileall -q src/rp_agent && uv run python -c "import rp_agent.tui, rp_agent.shell, rp_agent.core.chat; print('ok')"`
Expected: `ok`

- [ ] **Step 4: 收尾提交(如有未提交改动)并总结**

```bash
git status --short   # 确认仅预期的改动
git log --oneline -3
```

**TUI 视觉验证(用户执行)**:真实 Windows 控制台/Windows Terminal 运行 `uv run rp-agent shell`,进入 chat 模式发送消息,确认:四区圆角边框显示正常;输出区 `user>`(暖黄)与 `assistant>`(蓝)交替显示;输入区 prompt+输入框在框内;滚动不受边框影响。
