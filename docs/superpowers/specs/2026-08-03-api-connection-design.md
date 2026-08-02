# API 连接链路设计(配置 + 真实调用)

日期:2026-08-03
状态:已获用户口头批准

## 1. 背景

`rp-agent` 已完成 CLI 骨架、热重载、储存链路(data/api/ 目录已建)、交互式 shell。本阶段开发 **API 连接链路**:LLM API 连接的配置管理(data/api/ 下每连接一个 JSON 文件)+ 真实调用(OpenAI 兼容 `chat/completions`),为未来 RP 聊天内核打基础。

## 2. 目标与范围

### 做
- 新增 `src/rp_agent/api/` 包:models.py、store.py、client.py
- 配置管理:连接增删改查,基于现有 `storage.py`(safe_path/json_read/json_write)
- 真实调用:OpenAI 兼容 `chat/completions`,零依赖(标准库 `urllib.request`)
- Shell 集成:`api list/get/add/del/test` 命令
- 测试:models/store/client(本地假 OpenAI 服务器)

### 不做
- 不做流式(SSE)响应(后续聊天内核)
- 不做多轮对话/消息历史(聊天内核阶段)
- 不做密钥加密(明文,用户已确认)
- 不新增依赖

## 3. 技术方案

### 3.1 目录结构

```
src/rp_agent/api/
├── __init__.py          # 导出 ApiConnection、ApiError 等
├── models.py            # ApiConnection dataclass + validate
├── store.py             # 连接配置持久化
└── client.py            # OpenAI 兼容客户端
```

### 3.2 `models.py`

```python
@dataclass
class ApiConnection:
    name: str          # 连接名 = 文件名
    base_url: str      # 如 https://api.openai.com/v1
    api_key: str       # 明文
    model: str         # 默认模型名
    timeout: float = 30.0
```

`validate() -> None`:name 非空、base_url 以 `http://` 或 `https://` 开头、model 非空;非法抛 `ValueError`(含明确字段信息)。

### 3.3 `store.py`(基于 storage.py)

| API | 语义 |
|---|---|
| `list_connections() -> list[str]` | 列出 data/api/ 下所有 `.json` 连接名 |
| `get_connection(name: str) -> ApiConnection \| None` | 读取指定连接;缺失返回 None |
| `save_connection(conn: ApiConnection) -> None` | 写入 `data/api/<name>.json`(经 safe_path 防穿越) |
| `delete_connection(name: str) -> bool` | 删除连接文件;返回是否存在 |

- 路径:文件名 = `safe_path(f"api/{name}.json")`(复用 storage 防穿越)
- 写入前先 `conn.validate()`;读取时校验字段,损坏返回 None 并告警

### 3.4 `client.py`(OpenAI 兼容)

| API | 语义 |
|---|---|
| `chat(conn: ApiConnection, messages: list[dict], **kwargs) -> str` | POST `{base_url}/chat/completions`;`Authorization: Bearer <api_key>`;body `{"model": conn.model, "messages": messages, **kwargs}`;解析 `choices[0].message.content`;返回文本 |
| `test_connection(conn: ApiConnection) -> str` | 发 `[{"role": "user", "content": "ping"}]` 验证,返回模型回复 |
| `class ApiError(Exception)` | 网络错误/HTTP 非 2xx/响应格式异常 |

- 超时:conn.timeout
- 错误分类:连接失败(URLError/超时)、HTTP 状态(401/403 → 认证失败,其他 → 服务器错误)、响应格式异常(无 choices/content)

### 3.5 Shell 集成(扩展 shell.py)

| 命令 | 行为 |
|---|---|
| `api list` | 列出所有连接 |
| `api get <name>` | 显示连接详情(api_key 打码 `sk-***`) |
| `api add <name> <base_url> <model> [api_key]` | 新增/覆盖连接(api_key 缺省为空串) |
| `api del <name>` | 删除连接 |
| `api test <name>` | `test_connection()` 真实调用,打印模型回复 |

实现:shell 中新增 `api` 命令,按子参数分发(api list/get/add/del/test);未知子命令提示。

## 4. 错误处理

| 场景 | 处理 |
|---|---|
| 连接文件缺失 | `get_connection` 返回 None;shell 提示"连接不存在" |
| base_url 不可达/超时 | `ApiError`("连接失败: …") |
| HTTP 401/403 | `ApiError`("认证失败: …") |
| 响应无 content | `ApiError`("响应格式异常: …") |
| 配置校验失败 | `ValueError`,save 前拦截并提示 |

## 5. 测试策略

| 测试 | 覆盖 |
|---|---|
| `test_models.py` | 默认值;validate 通过;非法(base_url 非 http/https、name/model 空)抛 ValueError |
| `test_store.py` | save/get/list/delete 往返;缺失返回 None;删除不存在返回 False(monkeypatch `API_DIR` 到 tmp_path) |
| `test_client.py` | 标准库 `http.server` 起本地假 OpenAI 服务器:chat 成功返回文本、401 抛 ApiError、超时抛 ApiError |

## 6. 文件清单

```
src/rp_agent/api/__init__.py   # 新增
src/rp_agent/api/models.py     # 新增
src/rp_agent/api/store.py      # 新增
src/rp_agent/api/client.py     # 新增
src/rp_agent/shell.py          # 修改:api 命令组
tests/test_models.py           # 新增
tests/test_store.py            # 新增
tests/test_client.py           # 新增
tests/test_shell.py            # 修改:api 命令测试
```

## 7. 兼容性

- 现有 36 项测试保持通过
- 不新增依赖(`urllib`/`http.server` 标准库);`uv.lock` 不变
- 日志标准库 logging 输出 stderr

## 8. 未来扩展点(记录,不在本阶段)

- 流式(SSE)响应、多轮对话/消息历史
- 连接测试的并发/批量
- 密钥环境变量引用或加密(用户当前选择明文)
- Anthropic/本地模型非 OpenAI 兼容协议适配
