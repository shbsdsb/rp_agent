# chat 模式设计(占位 → 真实对话)

日期:2026-08-03
状态:已获用户口头批准(brainstorming 流程,6 问 6 答 + 方案确认 + 整体设计确认)

## 1. 背景

rp-agent 已具备:CLI 骨架、交互 shell(含 home/chat/rp/agent 工作模式与 `/` 转义)、API 连接链路(`client.chat()` 已就绪但未接线)、`data/chats/` 目录预留。本阶段把 chat 模式从"占位报错"升级为**真实 AI 对话**:多轮上下文、会话持久化、连接选择、点阵加载动画。

用户关键决策(ask 逐项确认 + `本次命令.md` 指定):
1. 会话模型:**多轮上下文 + 持久化到 `data/chats/<会话>.json`**
2. 连接机制:`api use <name>`(全局默认连接,**仅 home 模式可用**);`api set <name>`(会话内临时连接,**仅对话模式内可用**,持久化到会话 JSON 自动加载);开启新对话默认使用全局设置的连接
3. 会话管理:进入 chat 模式**默认新建**;`/new` 新建、`/list` 列出历史、`/load <id>` 继续旧会话
4. 输出方式:**首版阻塞**(复用 `client.chat()`)+ **点阵加载动画**(Braille spinner 帧 `⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`,100ms);流式输出留后续阶段
5. system prompt:`prompts/system/` 下新建 `chat.txt`、`rp.txt`、`agent.txt`,按模式加载
6. 长对话:**不截断**,超限由 API 报错,用户 `/new` 开新会话
7. 无全局连接时:提示手动设置(不自动选),列出可用连接

架构方案(用户全部采纳推荐):
- 主循环:**单循环扩展**(`run_shell` 仍是唯一主循环,chat 业务放 `core/chat.py`)
- 全局连接存储:`data/api/default.json`(由 `api/store.py` 扩展读写)
- 会话持久化:新增 `core/session.py`

## 2. 目标与范围

### 做
- `core/chat.py`:chat 模式业务(进入会话、处理消息、spinner、`/new` `/list` `/load`、会话内连接切换)
- `core/session.py`:`ChatSession` 数据类 + create/load/list/save/append,读写 `data/chats/`
- `api/store.py`:`get_default_connection` / `set_default_connection`(`data/api/default.json`)
- `shell.py`:chat 模式普通输入接入 chat 业务;拦截 `/new` `/list` `/load`;`api use`/`api set` 模式校验;维护当前模式状态
- `prompts/system/chat.txt`(真实内容)、`rp.txt`/`agent.txt`(占位一句)
- 测试:新增 `test_session.py`、`test_chat.py`;扩展 `test_store.py`/`test_shell.py`/`test_prompts.py`/`test_shell_lexer.py`

### 不做
- 不做流式输出(后续阶段)
- 不做角色扮演/agent 模式的真实业务(仅建 `rp.txt`/`agent.txt` 文件)
- 不做消息截断/token 计数
- 不做多行输入编辑(单行输入维持现状)
- 不加新依赖(threading 标准库)

## 3. 技术方案

### 3.1 `core/session.py` 会话模型与持久化

```python
@dataclass
class ChatSession:
    id: str
    created_at: str            # ISO8601 UTC
    updated_at: str
    connection: str            # ApiConnection.name,可为 ""
    messages: list[dict]       # [{"role": "user"|"assistant", "content": str}]

def create_session(connection: str = "") -> ChatSession
def save_session(session: ChatSession) -> None          # 原子写 data/chats/<id>.json
def load_session(session_id: str) -> ChatSession | None
def list_sessions() -> list[ChatSession]                # 按 updated_at 降序
def append_message(session: ChatSession, role: str, content: str) -> None
```

- id 格式:`YYYYmmdd-HHMMSS-xxxx`(时间戳 + 4 位随机,`secrets.token_hex(2)`),保证可读且唯一
- 文件路径走 `storage.safe_path(f"chats/{session_id}")`,防穿越;读缺失返回 None
- JSON 结构:
```json
{
  "id": "20260803-153000-8f3a",
  "created_at": "2026-08-03T15:30:00+00:00",
  "updated_at": "2026-08-03T15:30:05+00:00",
  "connection": "deepseek",
  "messages": [{"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好!"}]
}
```
- system 消息**不**入 JSON;每次请求时从 `prompts/system/chat.txt` 现加载(改文件即生效)

### 3.2 `api/store.py` 全局默认连接

```python
DEFAULT_CONN_FILE = API_DIR / "default.json"

def get_default_connection() -> ApiConnection | None   # 读 default.json 的 name,再 get_connection
def set_default_connection(name: str) -> None          # 写 {"name": name},校验存在由调用方负责
```

- 内容:`{"name": "deepseek"}`;文件缺失返回 None

### 3.3 `core/chat.py` 会话业务

对外提供(供 `shell.py` 调用):

```python
def new_session(connection: str = "") -> ChatSession        # create_session + 打印欢迎
def send_message(session: ChatSession, text: str) -> None   # 核心:user 消息→spinner→client.chat→assistant
def list_sessions() -> None                                  # 打印 /list 结果
def load_session(session_id: str) -> ChatSession | None      # /load 实现
def set_connection(session: ChatSession, name: str) -> None  # api set 实现:校验连接存在并更新会话
def system_prompt() -> str | None                            # 读 prompts/system/chat.txt
```

`send_message` 流程:
1. `append_message(session, "user", text)` 并 `save_session`(先保存,防请求中断丢失)
2. 解析连接:`get_connection(session.connection)`;None → 打印"未设置连接:请用 /api set <name> 或回 home 用 api use <name>",返回
3. 构造 messages:`[{"role":"system","content":system_prompt()}]`(若非 None)+ `session.messages` 全量(不截断)
4. 启动 spinner(点阵帧 `['⠋','⠙','⠹','⠸','⠼','⠴','⠦','⠧','⠇','⠏']`,100ms,后台线程 `\r` 重写;非 tty 退化为打印一行"正在请求…"不启动线程)
5. `client.chat(conn, messages)`;捕获 `ApiError`
6. 停 spinner;成功 → 打印回复 → `append_message(session, "assistant", reply)` + `save_session`;失败 → 打印错误(用户消息保留,可重发或 `/new`)

spinner 实现(chat.py 内私有):
```python
@contextmanager
def _spinner(label: str = "正在请求"):
    if not sys.stdin.isatty():
        print(f"{label}…", flush=True)
        yield
        return
    frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    stop = threading.Event()
    def _run():
        i = 0
        while not stop.is_set():
            sys.stdout.write(f"\r{frames[i % len(frames)]} {label}…")
            sys.stdout.flush()
            i += 1
            time.sleep(0.1)
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join()
        sys.stdout.write("\r" + " " * 40 + "\r")  # 清 spinner 行
        sys.stdout.flush()
```

### 3.4 `shell.py` 模式分发扩展

- 新增模块级 `_current_mode: Mode = "home"` 与 `_chat_session: ChatSession | None = None`(chat 模式会话状态),`run_shell` 每轮更新 `_current_mode`;两者供 `_cmd_api` 的 use/set 校验与会话更新访问(单文件内共享,避免改所有 handler 签名)
- chat 模式普通输入(非 `/`)分发改为:调用 `core/chat.py` 的 `send_message(_chat_session, text)`(替换占位报错)
- chat 模式内新增转义命令(仅非 home 模式可用,home 模式仍为未知命令):
  - `/new` → `chat.new_session(默认连接)`,结果赋给 `_chat_session`
  - `/list` → `chat.list_sessions()`
  - `/load <id>` → `chat.load_session(id)`,成功则赋给 `_chat_session`
- 着色:`_CHAT_COMMANDS = {"new", "list", "load"}` 并入 `_KNOWN_COMMANDS`(chat 模式有效转义命令显示为黄色);`_COMMAND_ARGS["api"]` 增加 `"use"`、`"set"`(位置子命令,非选项,`api/args.py` 的 `KNOWN_OPTIONS` 不动)
- `_dispatch_api` 增加 `use`/`set` 分支(校验在分支内):
  - `use <name>`:`_current_mode != "home"` → 打印"api use 仅可在 home 模式使用";home 模式 → 校验连接存在 → `set_default_connection(name)`
  - `set <name>`:`_current_mode == "home"` → 打印"api set 仅可在对话模式内使用";非 home → 校验连接存在 → 更新 `_chat_session.connection` 并保存会话 JSON

### 3.5 进入 chat 模式流程

1. 首次进入 chat 模式(或 `/new`):`new_session(默认连接)` —— 读 `get_default_connection()`;有 → 显示 `会话 <id> | 连接 <name> | 模型 <model>`;无 → 打印提示 + 列出可用连接(不自动选)
2. 会话状态加载后,普通输入走 `send_message`

### 3.6 system prompt

- `prompts/system/chat.txt`(新建,真实内容,如:"你是一个乐于助人的 AI 助手。请用简洁、准确的中文回答。")
- `prompts/system/rp.txt`、`agent.txt`(新建,占位一句,本期不加载)
- `system_prompt()` 用 `Path(__file__)` 定位 `../prompts/system/chat.txt`;缺失/读失败返回 None(无 system 降级)

### 3.7 `api use` / `api set` 帮助

- `help_data.py` 的 `api` 条目 params 增加:
  - `("use <name>", "设置全局默认连接(仅 home 模式)")`
  - `("set <name>", "设置当前会话连接(仅对话模式内)")`

## 4. 测试策略

| 测试 | 内容 |
|---|---|
| `tests/test_session.py`(新增) | create/append/save/load/list 往返;JSON 结构;id 唯一性;safe_path 防穿越;文件缺失返回 None |
| `tests/test_chat.py`(新增) | `send_message` monkeypatch `client.chat`:成功追加 assistant 并保存;ApiError 打印错误且不追加;无连接报错提示;`system_prompt` 读取;spinner 非 tty 退化(无线程);`new_session` 默认连接提示/列出 |
| `tests/test_store.py`(扩展) | default.json 读写、缺省 None、覆盖写 |
| `tests/test_shell.py`(扩展) | chat 模式普通输入调用 chat 处理(占位报错消失);`/new` `/list` `/load` 分发;`api use` home 可用/非 home 拒绝;`api set` 非 home 可用/home 拒绝 |
| `tests/test_shell_lexer.py`(扩展) | `use`/`set` 为 `api` 有效参数;`new`/`list`/`load` 着色(作为 chat 转义命令,若加入着色集合) |
| `tests/test_prompts.py`(扩展) | chat.txt/rp.txt/agent.txt 存在且非空 |

## 5. 文件清单

```
src/rp_agent/core/chat.py        # 新增:会话业务(替换占位 run)
src/rp_agent/core/session.py     # 新增:ChatSession + 持久化
src/rp_agent/api/store.py        # 修改:default connection 读写
src/rp_agent/shell.py            # 修改:chat 输入分发、/new /list /load、api use/set 校验、_current_mode
src/rp_agent/help_data.py        # 修改:api 条目加 use/set 说明
src/rp_agent/prompts/system/chat.txt  # 新增:chat system 提示词
src/rp_agent/prompts/system/rp.txt    # 新增:占位
src/rp_agent/prompts/system/agent.txt # 新增:占位
tests/test_session.py            # 新增
tests/test_chat.py               # 新增
tests/test_store.py              # 修改
tests/test_shell.py              # 修改
tests/test_shell_lexer.py        # 修改
tests/test_prompts.py            # 修改
```

## 6. 兼容性

- 默认行为:`rp-agent shell` 仍 home 模式进入;`rp-agent chat` 仍预进入 chat 模式(占位报错 → 真实对话,属预期变更)
- rp/agent 模式维持占位报错(本期不实现)
- 既有 113 项测试保持通过(占位报错相关断言需更新:chat 模式普通输入不再报"[chat] 对话功能尚未实现")
- 无新依赖;spinner 颜色/帧遵循非 tty 自动禁用原则
- 会话 JSON 为新增数据,无历史数据迁移问题
