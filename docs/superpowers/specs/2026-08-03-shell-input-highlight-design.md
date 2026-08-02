# Shell 输入实时语法着色设计(prompt_toolkit)

日期:2026-08-03
状态:已获用户口头批准;依赖 prompt_toolkit 已通过 ask 确认

## 1. 背景

用户希望在 shell 输入命令时**实时按语义着色**(命令黄、参数亮天蓝、选项灰,类似 fish/zsh 语法高亮)。纯终端回显技巧(input_prompt)只能整行同色,无法区分语义。引入 `prompt_toolkit` 实现实时词法高亮。

## 2. 目标与范围

### 做
- `uv add prompt_toolkit`(已通过 ask 确认)
- `shell.py` 新增 `ShellLexer`(实时词法着色)+ `ShellStyle` + `_read_line`(tty 用 pt_prompt,非 tty 回退 input)
- 顺带获得方向键历史导航(`InMemoryHistory`)
- 退役 `term.input_prompt()` / `term.reset_after_input()`(不再需要)
- 测试:test_shell_lexer.py 新增;test_shell.py 保持注入式;test_term.py 删 input_prompt 相关

### 不做
- 不做 Tab 补全(未来)
- 不改 help 概览/详细帮助(已完成)
- 不改 CLI 侧

## 3. 技术方案

### 3.1 依赖

`uv add prompt_toolkit`(纯 Python)。依赖策略:允许添加,添加前 ask 确认(已完成)。

### 3.2 `shell.py` 输入层

| 组件 | 语义 |
|---|---|
| `ShellLexer(prompt_toolkit.lexers.Lexer)` | `lex_document` 按行分词:首 token 为已知命令(`_COMMANDS` 键或 HELP_ENTRIES 别名)→ `class:cmd`;`-` 前缀 → `class:opt`;其他 → `class:param`;空格映射 `class:space` |
| `ShellStyle(prompt_toolkit.styles.Style)` | `{"cmd": "ansiyellow bold", "opt": "ansigray", "param": "ansibrightcyan"}` |
| `_read_line() -> str` | `sys.stdin.isatty()` 时:`pt_prompt(text=PROMPT_TEXT, lexer=ShellLexer(), style=ShellStyle(), history=_pt_history)`;否则回退 `input(PROMPT_TEXT)` |
| `run_shell(_input=...)` | 默认 `_input = _read_line`;测试注入 `_feed` 时绕过 prompt_toolkit(行为不变) |

- 提示符 `rp-agent> `(PROMPT_TEXT)保持**白色纯文本**(用户要求)
- `_pt_history = InMemoryHistory()`:方向键上下历史导航(Windows 也生效,bonus)

### 3.3 退役项

- `term.input_prompt()` / `term.reset_after_input()` 删除
- `term.blue` 保持亮天蓝 `\033[96m`(help 参数色不变)

## 4. 兼容与测试

| 项 | 处理 |
|---|---|
| 现有 test_shell.py(注入 _feed) | 不经过 prompt_toolkit,行为不变 |
| 非 tty / 管道 | `_read_line` 回退 input(),纯文本 |
| test_term.py | 删除 input_prompt 2 项,保留颜色 4 项 |
| 新增 test_shell_lexer.py | ShellLexer token 分类 |

## 5. 测试策略

| 测试 | 覆盖 |
|---|---|
| `test_shell_lexer.py`(新增) | "config"→cmd;"api list"→cmd+param;"x --help"→param+opt;未知首词→param;空白保留 |
| `test_shell.py`(保留) | 注入式输入行为不变(11 项) |
| `test_term.py`(修改) | 删除 input_prompt 2 项;保留 4 项颜色(blue=`\033[96m`) |

## 6. 文件清单

```
src/rp_agent/shell.py       # 修改:ShellLexer/ShellStyle/_read_line/run_shell 默认输入
src/rp_agent/term.py        # 修改:删除 input_prompt/reset_after_input
tests/test_shell_lexer.py   # 新增
tests/test_shell.py         # 保留(不动)
tests/test_term.py          # 修改:删 input_prompt 测试
pyproject.toml / uv.lock    # uv add prompt_toolkit
```

## 7. 兼容性

- 现有 62 项测试中:2 项 input_prompt 删除 → 60 项保留 + 新增 lexer 测试
- 注入式测试机制不变;非 tty 行为不变
- 日志仍标准库 logging

## 8. 未来扩展点(记录,不在本阶段)

- Tab 补全(completer,基于 _COMMANDS 与连接名)
- 多行输入、括号配对高亮
