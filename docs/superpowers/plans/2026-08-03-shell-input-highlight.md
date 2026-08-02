# Shell 输入实时语法着色实施计划(prompt_toolkit)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 prompt_toolkit 实现 shell 输入实时语法着色(命令黄/选项灰/参数亮天蓝),并获得方向键历史导航;退役 input_prompt 回显技巧。

**Architecture:** `uv add prompt_toolkit`;`shell.py` 新增 `ShellLexer`(按 token 分类 cmd/opt/param/space)、`SHELL_STYLE`、`_read_line`(tty 用 `pt_prompt`,非 tty 回退 `input`);`run_shell` 默认 `_input=_read_line`(注入测试机制不变);`term.py` 删除 `input_prompt`/`reset_after_input`。

**Tech Stack:** Python 3.14、prompt_toolkit(新依赖,已 ask 确认)、pytest。

## Global Constraints

- Python >= 3.14;测试一律 `uv run pytest`
- **新依赖 prompt_toolkit 已通过 ask 确认**(依赖策略:添加前 ask);用 `uv add prompt_toolkit` 管理
- 提示符 `rp-agent> ` 保持白色纯文本(PROMPT 常量)
- 着色规则:命令黄(`ansiyellow bold`)、选项灰(`ansigray`)、参数亮天蓝(`ansibrightcyan`)
- 测试注入机制不变:run_shell 的 `_input` 参数可注入,注入时绕过 prompt_toolkit
- 现有 62 项测试中 2 项 input_prompt 测试删除,其余保持
- 工作分支 `feat/api-connection`(延续)

---

### Task 1: 添加 prompt_toolkit + ShellLexer 实时着色

**Files:**
- Modify: `pyproject.toml` / `uv.lock`(`uv add prompt_toolkit`)
- Modify: `src/rp_agent/shell.py`
- Modify: `src/rp_agent/term.py`
- Create: `tests/test_shell_lexer.py`
- Modify: `tests/test_term.py`

**Interfaces:**
- Consumes: `_COMMANDS`、`HELP_ENTRIES`(现有)
- Produces:
  - `ShellLexer(prompt_toolkit.lexers.Lexer)`:`lex_document(document)` 返回 `get_line(lineno) -> list[tuple[str, str]]`
  - `SHELL_STYLE: Style`
  - `_read_line(prompt: str) -> str`:tty 用 `pt_prompt`,非 tty 回退 `input(prompt)`
  - `run_shell(_input: Callable[[str], str] = _read_line)`:循环内 `line = _input(PROMPT)`(不再用 input_prompt/reset_after_input)

- [ ] **Step 1: 添加依赖(已 ask 确认)**

```bash
export PATH="$(cygpath -u "$LOCALAPPDATA/Microsoft/WinGet/Packages/astral-sh.uv_Microsoft.Winget.Source_8wekyb3d8bbwe"):$PATH"
uv add prompt_toolkit
```
Expected: 安装成功,`pyproject.toml` 增加 `prompt_toolkit`,生成 `uv.lock` 更新。

- [ ] **Step 2: 写失败测试 `tests/test_shell_lexer.py`**

```python
from rp_agent.shell import ShellLexer


def _tokens(text: str):
    lexer = ShellLexer()
    doc = type("Doc", (), {"text": text})()
    get_line = lexer.lex_document(doc)
    return [(style, frag) for style, frag in get_line(0) if frag]


def test_known_command_is_cmd():
    assert _tokens("config") == [("class:cmd", "config")]


def test_command_and_param():
    assert _tokens("api list") == [
        ("class:cmd", "api"),
        ("class:space", " "),
        ("class:param", "list"),
    ]


def test_option_is_gray():
    assert _tokens("config --help")[2] == ("class:opt", "--help")


def test_unknown_first_word_is_param():
    assert _tokens("foobar x")[0] == ("class:param", "foobar")


def test_trailing_space_preserved():
    assert _tokens("config ")[1] == ("class:space", " ")
```

- [ ] **Step 3: 运行测试确认失败**

```bash
uv run pytest tests/test_shell_lexer.py -v
```
Expected: FAIL(`ImportError: cannot import name 'ShellLexer'`)

- [ ] **Step 4: 修改 `src/rp_agent/shell.py` 与 `src/rp_agent/term.py`**

`shell.py` import 区追加:
```python
import sys

from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.shortcuts import prompt as pt_prompt
from prompt_toolkit.styles import Style
```

`term.py` 删除 `input_prompt`、`reset_after_input`、`_INPUT_ESCAPE`(保留 yellow/blue/gray/bold/_ENABLED/_ANSI/_RESET;`blue` 保持 `\033[96m` 亮天蓝)。

`shell.py` 中 `_COMMANDS` 定义之后、`run_shell` 之前追加:
```python
_KNOWN_COMMANDS: set[str] = set(_COMMANDS) | {
    a for e in HELP_ENTRIES for a in e["aliases"]
}

SHELL_STYLE = Style.from_dict(
    {
        "cmd": "ansiyellow bold",
        "opt": "ansigray",
        "param": "ansibrightcyan",
    }
)


class ShellLexer(Lexer):
    """实时词法着色:首词命令黄、-前缀选项灰、其他参数亮天蓝。"""

    def lex_document(self, document):
        def get_line(lineno: int):
            if lineno != 0:
                return []
            tokens: list[tuple[str, str]] = []
            parts = document.text.split()
            index = 0
            for i, part in enumerate(parts):
                start = document.text.find(part, index)
                if start > index:
                    tokens.append(("class:space", document.text[index:start]))
                if i == 0 and part in _KNOWN_COMMANDS:
                    style = "class:cmd"
                elif part.startswith("-") and len(part) > 1:
                    style = "class:opt"
                else:
                    style = "class:param"
                tokens.append((style, part))
                index = start + len(part)
            if index < len(document.text):
                tokens.append(("class:space", document.text[index:]))
            return tokens

        return get_line


_pt_history = InMemoryHistory()


def _read_line(prompt: str) -> str:
    """读取输入行:tty 用 prompt_toolkit(实时着色 + 方向键历史),否则回退 input。"""
    if sys.stdin.isatty():
        return pt_prompt(
            prompt,
            lexer=ShellLexer(),
            style=SHELL_STYLE,
            history=_pt_history,
        )
    return input(prompt)
```

`run_shell` 签名与循环修改:
```python
def run_shell(_input: Callable[[str], str] = _read_line) -> None:
    """交互式主循环。_input 可注入(测试用);Ctrl+C/Ctrl+D 正常退出。"""
    _history.clear()
    print(_BANNER)
    while True:
        try:
            line = _input(PROMPT)
        except (EOFError, KeyboardInterrupt):
            print("退出")
            return
        cmd, args = parse_line(line)
        ...
```
(移除原 `input_prompt(PROMPT)` 与 `reset_after_input()` 调用;PROMPT 已是纯文本 `"rp-agent> "`。)

- [ ] **Step 5: 修改 `tests/test_term.py`(删除 input_prompt 两项)**

删除:
```python
def test_input_prompt_when_enabled(monkeypatch):
    ...
def test_input_prompt_when_disabled(monkeypatch):
    ...
```
保留 4 项颜色测试(blue 断言 `\033[96m`)。

- [ ] **Step 6: 运行测试确认通过**

```bash
uv run pytest tests/test_shell_lexer.py tests/test_term.py tests/test_shell.py -v
```
Expected: lexer 5 passed + term 4 passed + shell 11 passed = 20 passed

- [ ] **Step 7: 手动冒烟(非 tty 回退,验证 shell 仍正常)**

```bash
printf "config --help\nexit\n" | uv run rp-agent shell
```
Expected: 输出详细帮助并退出(非 tty 走 input 回退,无异常)。

- [ ] **Step 8: 提交**

```bash
git add pyproject.toml uv.lock src/rp_agent/shell.py src/rp_agent/term.py tests/test_shell_lexer.py tests/test_term.py
git commit -m "feat: shell 输入实时语法着色(ShellLexer/prompt_toolkit)+ 方向键历史"
```

---

### Task 2: 全量验证与收尾

**Files:**
- Modify: `README.md`(补充输入着色说明)

**Interfaces:**
- Consumes: Task 1 产物
- Produces: 全绿测试套件 + 完整 git 历史

- [ ] **Step 1: 运行全量测试**

```bash
uv run pytest -v
```
Expected: 65 passed(62 - 2 input_prompt + 5 lexer)

- [ ] **Step 2: 更新 README.md(在"交互式 Shell"章节内追加一行)**

```markdown
交互终端中,输入命令实时着色:命令黄色、参数亮天蓝、`--选项` 灰色;支持方向键历史。
```

- [ ] **Step 3: 确认工作树整洁并提交收尾**

```bash
git status --short
git add -A
git commit -m "chore: shell 输入实时着色完成(README 更新)"
git log --oneline
```
Expected: `git log --oneline` 显示连续提交历史。

---

## 验收清单(对照 spec)

- [ ] `uv add prompt_toolkit` 已安装(ask 确认)→ spec §3.1
- [ ] ShellLexer:命令黄/选项灰/参数亮天蓝/空白保留 → spec §3.2
- [ ] `_read_line` tty 用 pt_prompt(带方向键历史),非 tty 回退 input → spec §3.2
- [ ] 提示符 `rp-agent> ` 白色纯文本;run_shell 注入测试机制不变 → spec §3.2、§4
- [ ] `term.input_prompt`/`reset_after_input` 已退役,test_term 删 2 项 → spec §3.3
- [ ] 现有测试保持,总计 65 passed → spec §7
