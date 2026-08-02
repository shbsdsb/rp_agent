# 交互式 Shell 输入口设计

日期:2026-08-03
状态:已获用户口头批准

## 1. 背景

`rp-agent` 当前所有命令"即执行即退"(hello 等),终端没有交互输入口,不便测试命令。本阶段新增 `shell` 子命令:交互式 REPL,供用户测试配置/存储/冒烟等命令。

## 2. 目标与范围

### 做
- 新增子命令 `uv run rp-agent shell`,进入交互式 REPL
- 新增 `src/rp_agent/shell.py`:主循环 + 内置调试命令集
- `cli.py` 注册 `shell` 子命令
- 测试 `tests/test_shell.py`

### 不做
- 不做方向键历史导航的跨平台完整方案(Windows 用内存历史 + `history` 命令)
- 不做未来 chat/角色卡交互(本阶段面向现有能力测试)
- 不新增依赖(标准库 `readline` 仅类 Unix 可选启用,Windows 不做)

## 3. 技术方案

### 3.1 入口

`uv run rp-agent shell` 进入 REPL;提示符 `rp-agent> `;`exit`/`quit` 退出;Ctrl+C / Ctrl+D 也可退出;空行忽略。

### 3.2 `shell.py` 组件

| 组件 | 语义 |
|---|---|
| `parse_line(line: str) -> tuple[str, list[str]]` | 纯函数:输入行 → (命令名, 参数列表);`strip()` + `split()`;空行 → `("", [])` |
| `run_shell(_input: Callable[[str], str] = input) -> None` | 主循环;`_input` 可注入(测试用);banner + 提示符 + 分发;KeyboardInterrupt/EOFError 正常退出 |
| `_COMMANDS: dict[str, Callable[[list[str]], None]]` | 命令 → 处理器映射 |

### 3.3 命令集

| 命令 | 行为 |
|---|---|
| `help` / `?` | 列出可用命令与说明 |
| `config` | 打印当前配置字段(如 `log_level=INFO`) |
| `reload` | `reload_config()`,打印配置是否变化 |
| `storage` | `ensure_dirs()` + 打印 data 及四子目录内容 |
| `hello` | 冒烟:问候输出 + INFO 日志(验证命令→配置→日志链路) |
| `history` | 打印本次会话输入历史 |
| `exit` / `quit` | 退出 shell |
| 未知命令 | 打印提示"未知命令,输入 help 查看",不退出 |
| 空行 | 忽略 |

### 3.4 `cli.py` 集成

```python
@app.command()
def shell() -> None:
    """进入交互式 shell(测试命令用)。"""
    from rp_agent.shell import run_shell
    run_shell()
```

### 3.5 历史记录

- 会话内维护 `list[str]` 历史,`history` 命令打印
- 类 Unix:可选 `readline` 支持方向键(若可用);Windows:不启用方向键(零依赖)
- 空行与重复行不入历史

## 4. 错误处理

| 场景 | 处理 |
|---|---|
| 未知命令 | 打印提示,不退出 |
| 命令处理器异常 | `logger.exception`,shell 继续 |
| Ctrl+C | 打印退出提示,正常退出 |
| Ctrl+D / 非交互 stdin | 正常退出 |

## 5. 测试策略(`tests/test_shell.py`)

| 测试 | 覆盖 |
|---|---|
| `test_parse_line` | 空白剥离、参数切分、空行 |
| `test_run_shell_sequence` | 注入输入序列 `["hello", "config", "exit"]` 验证执行与退出 |
| `test_run_shell_unknown_command` | 未知命令提示且不退出(注入序列含未知命令后 exit) |
| `test_run_shell_eof` | 注入抛 EOFError 的输入 → 正常退出 |
| `test_help_lists_commands` | help 输出包含全部命令名 |

## 6. 文件清单

```
src/rp_agent/shell.py    # 新增:REPL 主循环 + 命令集
src/rp_agent/cli.py      # 修改:注册 shell 子命令
tests/test_shell.py      # 新增:测试
```

## 7. 兼容性

- 不修改现有行为;现有 30 项测试保持通过
- 不新增依赖(`uv.lock` 不变)
- 日志仍为标准库 logging 输出 stderr

## 8. 未来扩展点(记录,不在本阶段)

- 方向键历史导航(Windows 原生或 prompt_toolkit,需评估依赖)
- 补全(Tab)与子命令帮助
- chat/角色卡交互命令
