# hotfix:help 对齐 / config help / storage 重构 + chat 命令扩展 设计

日期:2026-08-03
状态:已获用户口头批准(brainstorming 流程,3 问 3 答 + 设计确认)

## 1. 背景

用户对 hotfix 分支提出三项热修复 + 一项命令扩展:
1. help 概览页命令对齐不统一(短命令 1 个 tab、长命令 2 个 tab)
2. `config --help` 太简陋,没有配置字段解释
3. `storage` 命令输出杂乱,整体删除;数据查看改为专门命令(`api list` / `chat list`)
4. (扩展)新增 `chat` 子命令系统:list/get/load/rename;rename 支持 prompt_toolkit tab 补全交互(zsh 式,用户明确"有可用库直接调用")

## 2. 目标与范围

### 做
- help 概览:命令名按最大宽度对齐(替代 `\t`)
- `config` help 条目补充字段解释(log_level/timeout/config timeout <秒>)
- 删除 `storage` 命令(`_COMMANDS` + `HELP_ENTRIES`);`storage.py` 底层保留
- `chat` 注册为顶层命令:`_cmd_chat` 分发 list/get/load/rename;无参数 `chat` 仍进入 chat 模式
- `ChatSession` 新增 `name` 字段;JSON 兼容旧文件
- rename:chat 模式内 `/rename <新名>`;外部 `chat rename`;`chat rename ` 输入时 tab 补全会话列表(prompt_toolkit `WordCompleter`,方向键选择)
- 测试更新与新增

### 不做
- 不做流式输出、不做 chat get 的消息分页、不做 name 的唯一性强制(重名提示用 id)
- 不删 `storage.py` 底层(api/store、core/session 依赖其原子写/安全路径)
- 不引入新依赖(prompt_toolkit 已有)

## 3. 技术方案

### 3.1 help 概览对齐(`shell.py` `_cmd_help`)

现实现:`print(f"  {yellow(name)}\t{e['desc']}")`(shell.py:107)。

改为:先收集所有命令名(含别名),计算最大显示宽度,`ljust` 对齐:

```python
def _cmd_help(args: list[str]) -> None:
    if args:
        _print_command_help(args[0])
        return
    print("可用命令:")
    names = []
    for e in HELP_ENTRIES:
        name = e["command"]
        if e["aliases"]:
            name += "/" + "/".join(e["aliases"])
        names.append(name)
    width = max(len(n) for n in names)
    for e, name in zip(HELP_ENTRIES, names):
        print(f"  {yellow(name.ljust(width))}  {e['desc']}")
    print("  输入 <命令> --help 查看详细用法")
```

对齐分隔用两个空格(替代 `\t`),所有 desc 同一列。

### 3.2 config help 条目(`help_data.py`)

`config` 条目改为:

```python
{
    "command": "config",
    "aliases": [],
    "desc": "显示当前配置(config timeout <秒> 可修改超时)",
    "usage": "config [timeout <秒>]",
    "params": [
        ("log_level", "日志级别:INFO/DEBUG/WARNING/ERROR(env RP_AGENT_LOG_LEVEL 覆盖)"),
        ("timeout", "全局网络超时(秒),默认 300(env RP_AGENT_TIMEOUT 覆盖)"),
        ("timeout <秒>", "设置全局超时并写入配置文件"),
    ],
},
```

### 3.3 删除 storage 命令

- `shell.py` `_COMMANDS` 删除 `"storage": (...)` 行(第 523 行)
- `help_data.py` 删除 `storage` 条目
- `shell.py` 删除 `_cmd_storage` 函数(第 94-99 行)
- 删除 `shell.py` 第 28 行 `from rp_agent.storage import DATA_DIR, ensure_dirs`(已确认仅 `_cmd_storage` 使用这两个名字)
- `storage.py` 底层保留——`core/session.py`、`api/store.py` 仍依赖其原子写/安全路径

### 3.4 chat 子命令系统(`shell.py`)

- `_COMMANDS` 增加:`"chat": ("会话管理(chat list/get/load/rename)", _cmd_chat)`
- `_cmd_chat(args)` + `_dispatch_chat(sub, rest)`(仿 `_cmd_api`/`_dispatch_api` 模式):

```python
def _cmd_chat(args: list[str]) -> None:
    if not args:
        print(f"用法: {_colorize_usage('chat <list|get|load|rename> ...')}")
        return
    _dispatch_chat(args[0], args[1:])


def _dispatch_chat(sub: str, rest: list[str]) -> None:
    if sub == "list":
        _chat_business("list_sessions")()
    elif sub == "get":
        _chat_get(rest)
    elif sub == "load":
        _chat_load(rest)
    elif sub == "rename":
        _chat_rename(rest)
    else:
        print(f"未知子命令: {sub}(用法: chat <list|get|load|rename> ...)")
```

- `run_shell` 的 `_MODE_COMMANDS` 分支调整:仅当 `cmd == "chat"` 且 `not args`(无参数)时切换模式;`chat --help` 走 `_print_command_help`(chat 已入 HELP_ENTRIES,补充子命令 params);`chat <子命令>` 走 `_COMMANDS` 分发:

```python
        if cmd in _MODE_COMMANDS and (cmd != "chat" or not args):
            mode = _MODE_COMMANDS[cmd]
            if mode == "chat":
                _chat_session = _chat_business("new_session")()
            continue
```

注意:`--help` 检查在前(`chat --help` 显示帮助),`chat list` 等带参数不再触发模式切换。

- `_COMMAND_ARGS["chat"] = {"list", "get", "load", "rename"}`(着色)

### 3.5 `ChatSession.name` 字段(`core/session.py`)

```python
@dataclass
class ChatSession:
    id: str
    created_at: str
    updated_at: str
    connection: str = ""
    name: str = ""            # 可读名称,默认空(= 显示 id)
    messages: list[dict] = field(default_factory=list)
```

- `create_session`:name 默认 `""`
- `save_session`:JSON 增加 `"name": session.name`
- `load_session`:读 `name`(旧文件缺省 `""`)
- `chat list` 显示:`{name or id}`;`chat get` 显示 name 与消息列表

### 3.6 chat 子命令行为(`core/chat.py` 新增函数)

```python
def find_session(key: str) -> ChatSession | None
    # 按 id 精确,或按 name 匹配(重名时打印提示用 id),找不到返回 None

def get_session(key: str) -> None
    # chat get:打印会话详情(含逐条消息 role/content)

def load_into_session(key: str) -> ChatSession | None
    # chat load:加载会话(打印提示),shell 将其赋给 _chat_session 并切 chat 模式

def rename_session(session: ChatSession, new_name: str) -> None
    # 更新 name + save + 打印;空名拒绝

def rename_by_key(key: str, new_name: str) -> None
    # chat rename 外部路径:find_session → rename_session
```

- `/rename <新名>`(chat 模式内):`run_shell` 的 `_CHAT_COMMANDS` 增加 `"rename"` 分支,调用 `_chat_business("rename_session")(_chat_session, new_name)`

### 3.7 rename tab 补全(prompt_toolkit)

- `_read_line` 增加 `completer` 参数:仅当输入匹配 `chat rename` 前缀时提供补全:

```python
def _chat_rename_completer() -> Completer | None:
    """动态补全:chat rename 后的第一个参数补全会话名列表。"""
    from prompt_toolkit.completion import WordCompleter

    names = _chat_business("session_names")()   # [name or id, ...]
    return WordCompleter(names, ignore_case=True) if names else None
```

- `_read_line` 中用 `prompt_toolkit.shortcuts.prompt` 的 `completer` 参数传入(非 tty 回退无需):
  - 实现:读取输入前检查当前行前缀无法提前得知,故用 **DynamicCompleter** 在输入时根据 buffer 文本判断:若 `buffer.text` 匹配 `chat rename` 且其后仅一个词(第一个参数位置)则启用补全
  - prompt_toolkit 补全菜单默认行为:Tab 打开菜单,↑↓ 选择,Enter/右箭头确认——即 zsh 式交互,直接复用库能力
- 交互流程:
  - `chat rename <旧名> <新名>` 两参 → 直接执行
  - `chat rename <旧名>` 一参 → 第二行 prompt 输入新名(无补全)
  - `chat rename `(无参)→ 第一行 tab 补全选旧名 → 第二行输入新名
- `session_names()`(core/chat.py):返回所有会话的 `name or id` 列表

### 3.8 帮助与着色

- `HELP_ENTRIES` 的 `chat` 条目 params 更新:

```python
("list", "列出全部会话(id/名称、时间、连接、消息数)"),
("get <id|name>", "查看会话详情(含消息列表)"),
("load <id|name>", "加载会话并进入 chat 模式"),
("rename <旧名> <新名>", "重命名会话;输入中 Tab 可补全选择"),
```

- `_COMMAND_ARGS["chat"] = {"list", "get", "load", "rename"}`;`_KNOWN_COMMANDS` 已含 chat(HELP_ENTRIES 派生)

## 4. 测试策略

| 测试 | 内容 |
|---|---|
| `tests/test_shell.py`(修改) | help 概览 desc 对齐(断言所有 desc 起始列一致或不再含 `\t`);`storage` 未知命令;`chat list/get/load/rename` 分发;`chat` 无参仍进模式 |
| `tests/test_help_data.py`(修改) | config 条目 params 非空且含 log_level/timeout;chat 条目含 list/get/load/rename;移除 storage 条目断言 |
| `tests/test_session.py`(扩展) | name 字段 roundtrip;旧 JSON 无 name 兼容 |
| `tests/test_chat.py`(扩展) | find_session 按 id/name;rename_session 更新+保存+空名拒绝;session_names 列表 |
| `tests/test_shell_lexer.py`(扩展) | `chat` 子命令 list/get/load/rename 为有效参数;`storage` 不再着色 |

## 5. 文件清单

```
src/rp_agent/shell.py          # 修改:help 对齐、删 storage、_cmd_chat 分发、_MODE_COMMANDS 调整、completer、/rename
src/rp_agent/help_data.py      # 修改:config/chat 条目、删 storage 条目
src/rp_agent/core/session.py   # 修改:name 字段
src/rp_agent/core/chat.py      # 修改:find_session/get_session/load_into/rename/session_names、/rename 支持
tests/test_shell.py            # 修改
tests/test_help_data.py        # 修改
tests/test_session.py          # 扩展
tests/test_chat.py             # 扩展
tests/test_shell_lexer.py      # 扩展
```

## 6. 兼容性

- `chat` 命令无参行为不变(进入 chat 模式);`chat <子命令>` 为新能力
- `storage` 命令移除——若有用例引用需删除;`storage.py` 底层不受影响
- 会话旧 JSON 无 `name` 字段 → 加载 `""`,显示 id,可正常 rename
- 零新依赖;tab 补全仅 tty 下生效(prompt_toolkit),非 tty 走 `input` 回退(无补全,可完整输入参数)
