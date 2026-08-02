# Help 概览与着色同步设计

日期:2026-08-03
状态:已获用户口头批准

## 1. 背景

用户确认:输入着色规则(**有效命令/有效参数/有效选项才变色**)维持现状,不需要修改。实际变更两点:
1. help 概览页命令名颜色与 prompt_toolkit 输入命令色同步(黄 bold)
2. help 概览页对齐方式改为制表符

## 2. 目标与范围

### 做
- `term.yellow` 升级为黄 bold(`\033[33m` → `\033[1;33m`),概览与 usage 命令色与输入着色(`ansiyellow bold`)同步
- `shell.py` `_cmd_help` 概览行改为制表符对齐:`  {yellow(name)}\t{desc}`
- 更新 `tests/test_term.py` 的 yellow 断言

### 不做
- 不改 ShellLexer / `_VALID_OPTIONS`(输入着色规则维持)
- 不改 help 详细页布局
- 不改帮助文案

## 3. 技术方案

### 3.1 `term.py`

`yellow` 的 ANSI 码 `\033[33m` → `\033[1;33m`(bold + 黄,与 prompt_toolkit `ansiyellow bold` 一致)。

### 3.2 `shell.py` 概览页

```python
for e in HELP_ENTRIES:
    name = e["command"]
    if e["aliases"]:
        name += "/" + "/".join(e["aliases"])
    print(f"  {yellow(name)}\t{e['desc']}")
```
- 删除 `width = max(...)` 计算(不再需要)
- 别名同行保留

## 4. 测试策略

| 测试 | 变更 |
|---|---|
| `test_term.py` | `test_colors_wrap_when_enabled` 中 yellow 断言 `\033[33m` → `\033[1;33m` |
| `test_shell_lexer.py` | 不改 |
| `test_shell.py` | 不改(概览 tab 对齐不影响现有断言:命令名与描述仍含于输出) |

## 5. 文件清单

```
src/rp_agent/term.py        # 修改:yellow ANSI 码
src/rp_agent/shell.py       # 修改:_cmd_help 概览 tab 对齐
tests/test_term.py          # 修改:yellow 断言
```

## 6. 兼容性

- 现有 68 项测试中仅 test_term 1 项断言更新;其余保持
- 行为变化:help 概览命令名变黄 bold、tab 对齐(视觉),逻辑不变
