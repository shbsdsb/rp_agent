# chat / rp / agent 三种 AI 工作模式(占位)设计

日期:2026-08-03
状态:已获用户口头批准(brainstorming 流程,4 问 4 答 + 整体设计确认)

## 1. 背景

rp-agent 已具备 CLI 骨架、交互 shell、API 连接链路(OpenAI 兼容客户端已就绪,但 `client.chat()` 未接线)。下一步规划三种 AI 工作方式:**AI 聊天(chat)、角色扮演(rp)、agent**。本阶段仅做占位:注册 3 个 CLI 子命令与对应文件,并在 shell 中引入工作模式切换,为后续接入真实对话能力打好交互骨架。

用户关键决策(ask 逐项确认):
1. 对应文件放 `core/` 下:`core/chat.py`、`core/rp.py`、`core/agent.py`
2. 进入模式后前缀由 `home>` 变为 `chat>` / `rp>` / `agent>`
3. 模式内普通输入(未来是对话内容)打印**灰色占位报错**,仍可继续输入
4. 模式内用 `/` 转义调用正常命令(如 `/api`),随时配置随时查看,不干扰对话
5. 模式内 `/exit` 回到 home;home 模式 `exit` 退出整个 shell
6. CLI 子命令 `rp-agent chat` / `rp` / `agent` 直接启动 REPL 并预进入对应模式

## 2. 目标与范围

### 做
- `cli.py` 注册 `chat` / `rp` / `agent` 三个子命令,各自调用 `core/*.py` 的 `run()`
- 新增 `core/chat.py`、`core/rp.py`、`core/agent.py`:各导出 `run()`,调用 `run_shell(initial_mode=...)`
- `shell.py` 引入模式状态:home / chat / rp / agent;前缀随模式变化
- 模式内普通输入 → 灰色占位报错;`/` 转义正常命令;`/exit` 回 home
- `_COMMANDS` 增加 chat/rp/agent(供 home 模式切换 + ShellLexer 着色);帮助补充模式说明
- 测试:`test_core.py` 新增,`test_shell.py` 扩展

### 不做
- 不实现真实对话/角色扮演/agent 逻辑(`client.chat()` 仍不接线)
- 不落盘对话内容(普通输入仅报错,不收集)
- 不改 API 链路、storage、config、watch
- 不加新依赖(prompt_toolkit 已在用)

## 3. 技术方案

### 3.1 模式状态与前缀(`shell.py`)

```python
Mode = Literal["home", "chat", "rp", "agent"]

def _prompt_for_mode(mode: Mode) -> str:
    return {"home": "home> ", "chat": "chat> ", "rp": "rp> ", "agent": "agent> "}[mode]
```

- `run_shell(initial_mode: Mode = "home")` 新增参数,REPL 从该模式开始
- 模式内 `prompt_toolkit` 的 prompt 前缀用 `_prompt_for_mode(mode)`

### 3.2 输入分发(模式内)

`run_shell` 主循环中,对当前模式分派:

| 输入 | home 模式 | chat/rp/agent 模式 |
|---|---|---|
| 以 `/` 开头 | 解析为正常命令(`/exit` 退出 shell) | 解析为正常命令(`/exit` 回 home) |
| 以 `exit` 开头 | 退出 shell(现状) | 当作对话内容 → 灰色占位报错 |
| 其他 | 走 `_COMMANDS`(chat/rp/agent 进入对应模式) | 对话内容 → 灰色占位报错 |

- `/` 转义实现:把 `/foo ...` 去掉 `/` 后走现有 `parse_line` + 命令分派,即模式内可调用 `api`、`help` 等全部正常命令
- 占位报错用 `term.gray()`(ANSI 灰,非 tty / NO_COLOR 自动禁用),文案示例:`[chat] 对话功能尚未实现(占位模式),/exit 返回 home`
- `/exit` 语义:chat/rp/agent 模式 → 切回 home;home 模式 → 退出 shell

### 3.3 CLI 子命令(`cli.py`)

```python
@app.command()
def chat() -> None:
    """AI 聊天模式(占位)。"""
    from rp_agent.core.chat import run
    run()

@app.command()
def rp() -> None:
    """角色扮演模式(占位)。"""
    from rp_agent.core.rp import run
    run()

@app.command()
def agent() -> None:
    """agent 模式(占位)。"""
    from rp_agent.core.agent import run
    run()
```

- 延迟 import,与 `shell` 命令的既有模式一致(cli.py:119)
- 命令名 `rp` 与包 `rp_agent` 前缀不冲突;注意 `core/rp.py` 模块名为 `rp`

### 3.4 `core/*.py` 占位模块

```python
# core/chat.py
def run() -> None:
    from rp_agent.shell import run_shell
    run_shell(initial_mode="chat")
```

rp/agent 同理。未来对话/角色扮演/agent 业务逻辑落在此处(接 `client.chat()`)。

### 3.5 帮助与着色

- `HELP_ENTRIES`(`help_data.py`)新增 chat/rp/agent 三条(命令 + 描述);`shell.py` `_COMMANDS` 同步新增三个命令分派(两处独立定义,均需新增)
- `ShellLexer` 通过 `_COMMANDS` 自动识别新命令着色,无需额外改动(`_KNOWN_COMMANDS` 由 `_COMMANDS` 派生,shell.py:441-453)
- help 概览/详细页补充:模式说明、`/` 转义说明、`/exit` 说明

## 4. 测试策略

| 测试 | 变更 |
|---|---|
| `tests/test_core.py`(新增) | chat/rp/agent 三模块 `run()` 存在且调用 `run_shell(initial_mode=对应模式)` |
| `tests/test_shell.py`(扩展) | ① home 模式输入 `chat` → 模式变 chat、前缀变 `chat>` ② 模式内普通输入 → 输出灰色占位报错且模式不变 ③ `/exit` → 回 home ④ `/api list` 在模式内可执行 ⑤ home 模式 `exit` 仍退出 shell ⑥ `run_shell(initial_mode="agent")` 从 agent 模式启动 |
| `tests/test_help_data.py`(扩展) | HELP_ENTRIES 含 chat/rp/agent |
| `tests/test_shell_lexer.py` | 若需,补 chat/rp/agent 命令着色断言 |

## 5. 文件清单

```
src/rp_agent/cli.py            # 修改:注册 chat/rp/agent 子命令
src/rp_agent/core/chat.py      # 新增:run() → run_shell(initial_mode="chat")
src/rp_agent/core/rp.py        # 新增:run() → run_shell(initial_mode="rp")
src/rp_agent/core/agent.py     # 新增:run() → run_shell(initial_mode="agent")
src/rp_agent/shell.py          # 修改:模式状态、前缀、/ 转义、占位报错、run_shell(initial_mode)
src/rp_agent/help_data.py      # 修改:HELP_ENTRIES 加 chat/rp/agent
tests/test_core.py             # 新增
tests/test_shell.py            # 修改:模式相关用例
tests/test_help_data.py        # 修改(如需)
```

## 6. 兼容性

- 默认行为不变:`rp-agent shell` 仍从 home 模式进入,前缀为 `home>`(上一轮 PROMPT 改动已生效)
- 新增命令不影响现有 hello/shell/api 流程
- 占位报错仅出现在 chat/rp/agent 模式内,home 模式行为与现状一致
- 无新依赖;颜色遵循 term.py 非 tty 自动禁用
