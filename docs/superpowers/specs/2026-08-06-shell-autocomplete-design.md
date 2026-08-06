# Shell 全范围 Tab 自动补全 — 设计文档

- 日期:2026-08-06
- 分支:`feat/shell-autocomplete`
- 状态:已获用户确认(范围、交互方式、实现方案、边界、测试、范围外)

## 背景与目标

`rp-agent` 交互 shell 已具备 prompt_toolkit 实时词法着色(`ShellLexer`):
有效命令黄、有效参数(蓝色子命令)亮天蓝、有效选项灰。但 Tab 补全目前
仅有会话名补全(`ChatSessionCompleter`,覆盖 `chat rename/get/load` 与
模式内 `/load` 的第一参数),命令名、子命令、选项、连接名均无补全。

目标:对所有"蓝色子命令"及周边词(命令名、选项、连接名/会话名)提供
prompt_toolkit Tab 自动补全,采用 dropdown 菜单交互。

## 已确认决策

- **补全范围:** 全范围 —— 第一词命令名 + 蓝色子命令 + 选项词 + 连接名/会话名
- **交互方式:** dropdown 菜单(prompt_toolkit 默认行为,无需 key binding)
- **实现方案:** 方案 A —— 单一 `ShellCompleter` 按 token 位置分发
- **数据源一致性:** 补全候选与 `ShellLexer` 着色共用同一数据源
  (`_KNOWN_COMMANDS` / `_COMMAND_ARGS` / `_VALID_OPTIONS`),
  保证"着色的词 = 可补全的词"

## 架构

### 新增 `ShellCompleter(Completer)`(`src/rp_agent/shell.py`)

`_read_line` 的 `pt_prompt` 的 `completer=` 由 `ChatSessionCompleter()` 改为
`ShellCompleter()`。

### 候选来源(与 ShellLexer 同源)

| 位置 | 补什么 | 数据源 |
|---|---|---|
| 第 1 词 | 命令名(含 `/` 转义变体) | `_KNOWN_COMMANDS` |
| 第 2 词 | 蓝色子命令 | `_COMMAND_ARGS[cmd]` |
| 第 3+ 词(以 `-` 开头) | 灰色选项 | `_VALID_OPTIONS`(= `KNOWN_OPTIONS`) |
| 第 3+ 词(位置参数) | 连接名 / 会话名 | `list_connections()` / `session_names()`(运行时读取) |

### 位置参数分发表

```python
_POSITIONAL_COMPLETERS: dict[str, dict[int, str]] = {
    "api get": {1: "connection"}, "api del": {1: "connection"},
    "api test": {1: "connection"}, "api pull": {1: "connection"},
    "api sync": {1: "connection"}, "api modify": {1: "connection"},
    "api use": {1: "connection"}, "api set": {1: "connection"},
    "chat get": {1: "session"}, "chat load": {1: "session"},
    "chat rename": {1: "session"}, "/load": {1: "session"},
}
```

- `api add` 不补位置参数(弃用形式的新 name 是新建的,补已有连接无意义);
  但 `--name` 等选项照常补全
- `chat rename` 第二参不补全(新名是新建的)

### 分派逻辑

按光标前的已输入词数定位,只补"正在输入的那个词":
1. 空行 → 全部命令名
2. 第 1 词 → 命令名(含 `/` 前缀变体:模式内 `/load` 等)
3. 第 2 词 → `_COMMAND_ARGS[cmd]` 的蓝色子命令
4. 第 3+ 词:
   - 当前词以 `-` 开头 → `_VALID_OPTIONS`(选项,`--xxx` 与 `-x`)
   - 否则 → 查 `_POSITIONAL_COMPLETERS[cmd+sub]` 的位置参数(连接名/会话名)

边界:
- 未知命令 / 未知子命令 → 不补全
- 无候选 → 安静返回,不打断输入(与现有 `ChatSessionCompleter` 一致)
- 动态数据读取失败(store 异常等)→ try/except 捕获,跳过动态候选,
  静态候选照常
- 大小写:沿用 `ignore_case=True`
- 只补"正在输入的词":光标前词已完整(后有空格)时不干扰后续词

### 合并 `ChatSessionCompleter`

`ChatSessionCompleter` 删除,其会话名逻辑并入 `ShellCompleter`(避免两个
completer 抢 Tab)。`tests/test_shell_completer.py` 相应改写。

## 错误处理

- 无候选 → 安静返回
- 动态数据读取失败 → 捕获异常,降级为静态候选
- 非 tty 回退 `input()` 不受影响(completer 只在 `pt_prompt` 分支生效)
- `/` 转义前缀:剥前缀后按已知命令处理,`/load` 走会话名补全

## 测试(测试驱动)

扩展 `tests/test_shell_completer.py`(沿用现有 `_complete`/`_names` helper):

| 用例 | 输入 | 期望 |
|---|---|---|
| 命令名补全 | `a` | 含 `api`/`agent` |
| 子命令补全 | `api li` | 含 `list` |
| 子命令不匹配 | `api zz` | 空 |
| 选项补全 | `api add --n` | 含 `--name` |
| 选项不匹配 | `api add --wat` | 空 |
| 连接名补全 | `api get ` | 含已保存连接 |
| 会话名补全(保留原测试) | `chat get ` | 含 `三体会话` |
| 第二参不补全 | `chat rename 三体会话 新` | 空 |
| `/load` 补全 | `/load 三体` | 含 `三体会话` |
| 未知命令不补全 | `foobar x` | 空 |

所有 `ShellLexer` 测试不受影响(`class:param`/`class:opt` 着色逻辑不动)。

## 明确不做(范围外)

- 不做 fuzzy/子串匹配,仅前缀补全(prompt_toolkit 默认)
- 不改动 `ShellLexer` 与着色逻辑
- 不引入新依赖(prompt_toolkit 已具备)
- `api add` 不补位置参数(弃用形式),但 `--name` 等选项照常补
