# Shell 颜色与 Help 增强设计

日期:2026-08-03
状态:已获用户口头批准(含灰色选项补充)

## 1. 背景

`rp-agent` 交互式 shell 已有基础命令集。本阶段增强终端可读性:命令/参数/选项着色(参考 winget help 样式),以及 help 页面增强(`<命令> --help` 详细用法、功能重合命令同行显示)。

## 2. 目标与范围

### 做
- 新增 `src/rp_agent/term.py`:ANSI 颜色工具(黄/蓝/灰/粗体),零依赖
- 新增 `src/rp_agent/help_data.py`:帮助数据表单(查询表单,存于 src/rp_agent 下)
- `shell.py` 修改:help 概览着色、`<命令> --help` 详细帮助、用法提示着色
- 测试:test_term.py、test_help_data.py、test_shell.py 扩展

### 不做
- 不改 CLI(--help 已由 Typer 提供;本次只改 shell 内 help)
- 不做颜色主题配置
- 不新增依赖

## 3. 技术方案

### 3.1 `term.py` — 终端颜色(零依赖 ANSI)

| API | 语义 |
|---|---|
| `supports_color() -> bool` | stdout isatty 且环境无 `NO_COLOR`;Windows 上 `ctypes.windll.kernel32.SetConsoleMode` 启用 VT 处理 |
| `yellow(text: str) -> str` | `\033[33m{text}\033[0m` |
| `blue(text: str) -> str` | `\033[34m{text}\033[0m` |
| `gray(text: str) -> str` | `\033[90m{text}\033[0m` |
| `bold(text: str) -> str` | `\033[1m{text}\033[0m` |
| 不支持颜色 | 各函数原样返回 text |

实现:模块级 `_ENABLED = supports_color()` 缓存;颜色函数据此开关。

### 3.2 `help_data.py` — 帮助数据表单

```python
HELP_ENTRIES: list[dict[str, object]] = [
    {
        "command": "help",
        "aliases": ["?"],
        "desc": "显示帮助(help | <命令> --help)",
        "usage": "help [命令]",
        "params": [("命令", "可选:查看指定命令的详细帮助")],
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
    # config / reload / storage / hello / history 同理,每条含 command/aliases/desc/usage/params
]
```

覆盖命令:help/?、config、reload、storage、hello、history、exit/quit、api。

### 3.3 `shell.py` 修改

- **help 概览页**:遍历 HELP_ENTRIES;命令名(含别名,如 `exit/quit`)**黄色**,描述正常色;对齐输出
- **`<命令> --help`**:`parse_line` 得 `(cmd, ["--help"])` 时,查 HELP_ENTRIES:
  - 找到 → 打印 usage(标签黄、选项灰、参数蓝)+ 每行参数名蓝 + 说明
  - 未找到 → 提示"未知命令: cmd"
- **用法提示着色**:`api` 命令的用法行:子命令名黄、`--xxx` 选项灰、`<参数>` 蓝

### 3.4 颜色规则(参考 winget)

| 元素 | 颜色 |
|---|---|
| 命令名 | 黄 |
| 参数名(`<name>`、`list`、`get` 等) | 蓝 |
| 有效选项(`--help`、`-h` 等 `-` 前缀) | 灰 |
| usage 标签 | 黄 |

capsys/非 tty 环境:`supports_color()` 为 False,输出纯文本(测试断言无 ANSI 转义)。

## 4. 错误处理

| 场景 | 处理 |
|---|---|
| `<命令> --help` 命令未知 | 提示"未知命令: cmd",不退出 |
| HELP_ENTRIES 缺条目 | 概览页跳过该命令(不崩溃) |
| Windows 旧终端不支持 VT | supports_color False,纯文本 |

## 5. 测试策略

| 测试 | 覆盖 |
|---|---|
| `test_term.py`(新增) | yellow/blue/gray 返回 ANSI 包裹;禁用时原样返回(monkeypatch `_ENABLED`) |
| `test_help_data.py`(新增) | 每条 entry 含 command/desc/usage;aliases 无重复;命令名唯一 |
| `test_shell.py`(扩展) | `help` 输出含同行 `exit/quit`;`config --help` 含 usage;`api --help` 含子命令参数;capsys 下无 `\033` 转义 |

## 6. 文件清单

```
src/rp_agent/term.py        # 新增
src/rp_agent/help_data.py   # 新增
src/rp_agent/shell.py       # 修改:help 概览/详细帮助/着色
tests/test_term.py          # 新增
tests/test_help_data.py     # 新增
tests/test_shell.py         # 修改
```

## 7. 兼容性

- 现有 50 项测试保持通过;不新增依赖;`uv.lock` 不变
- 非 tty 环境行为不变(纯文本)
- shell 命令行为不变(仅输出样式变化)

## 8. 未来扩展点(记录,不在本阶段)

- 颜色主题配置、256 色
- help 分页、搜索
- CLI(Typer)侧帮助与 shell 帮助统一
