# API 连接管理命令集重构设计

日期:2026-08-03
状态:已获用户口头批准(依据用户提供的 `本次命令.md` 设计文档,经头脑风暴确认调整)

## 1. 背景

现有 `api` 命令集(6 个子命令)功能简单:简易 split 解析、明文显示、无模型拉取。用户提供重构设计(本次命令.md),要求:新增 pull/sync/modify,升级 list/get/add/del/test,命名参数优先,交互式修改(nano 快捷键),安全脱敏。经头脑风暴确认:**加密存储暂缓(仅脱敏)**、**自写参数解析器**、**modify 完整版 + nano 快捷键**。

## 2. 目标与范围

### 做
- 新增 `api/args.py`:轻量参数解析器(`--key value`/`--flag`/位置参数)
- 命令集重构:list/get/add/del/test 升级 + 新增 pull/sync/modify
- `client.py` 新增 `list_models(conn) -> list[str]`(`GET {base_url}/models`)
- `store.py` 连接字段增加 `last_tested`(list -v 用)
- modify 交互式编辑:子提示符 + 依次编辑 + 静默密钥 + nano 快捷键(Ctrl+O/X/R/G)+ 底部提示栏
- 密钥脱敏(前4后4 `****`)、静默输入;旧位置参数保留 + 弃用警告

### 不做
- 不做密钥加密存储(用户确认暂缓,文件仍明文)
- 不做日志文件(~/.rp-agent/logs,文档第 6 节,后续)
- 不做 `keyring`/`cryptography` 依赖

## 3. 技术方案

### 3.1 `api/args.py` — 参数解析器(零依赖)

```python
def parse_args(argv: list[str]) -> tuple[dict[str, str], list[str]]:
    """解析 --key value / --flag / 位置参数。

    - `--name value` → {"name": "value"};`--verbose` 无值 → {"verbose": ""}
    - `--filter k=v` 原样存入;未知 `--xxx` 抛 ValueError
    - 其余为位置参数列表
    """
```

### 3.2 命令集总览

| 命令 | 行为 |
|---|---|
| `list` | 默认只显名称;`-v/--verbose` 表格(`名称\tBase URL\t模型\t最近测试`);`--filter model=gpt-4` 筛选 |
| `get <name>` | 显示字段;密钥脱敏前4后4(`sk-1234****5678`);不存在报错 |
| `add` | 命名参数 `--name --url --key [--model]`;已存在报错不覆盖;位置简写保留+弃用警告;可选 `--pull` 保存前拉取模型(失败中止) |
| `del <name>` | 二次确认 `y/N`;`--force` 跳过 |
| `test <name> [--timeout N]` | 探测连通性;成功/失败原因 |
| `pull` | `pull <name> [--set-default]` 或 `pull --url --key [--timeout]`(临时);调 `/models`,打印模型列表 |
| `sync <name> [--set-default]` | 测试 → 拉取模型 → 打印;`--set-default` 设第一模型为默认 |
| `modify <name>` | 交互式(默认)或 `--set field=value`(非交互) |

### 3.3 `client.py` 新增

```python
def list_models(conn: ApiConnection, timeout: float | None = None) -> list[str]:
    """GET {base_url}/models,解析 data[].id;错误复用 ApiError 分类。"""
```

### 3.4 `store.py` 扩展

- `ApiConnection` 增加 `last_tested: str = ""`(ISO 时间串;test/sync 成功时更新)
- `save_connection`/`get_connection` 读写该字段(缺失默认 "")

### 3.5 modify 交互式编辑(nano 风格)

- 子提示符 `rp-agent-modify-<name>>`;依次编辑 `Base URL → API Key(静默)→ Model`;回车保留原值
- `/字段` 直接跳转(`/model`、`/url`、`/key`)
- **底部固定提示栏**(prompt_toolkit `bottom_toolbar`):
  ```
  ^O 保存  ^X 放弃  ^R 重置  ^G 帮助
  ```
  - `Ctrl+O` 保存并退出;`Ctrl+X` 放弃退出;`Ctrl+R` 重置为原值;`Ctrl+G` 帮助
- 校验:URL 以 http(s):// 开头、非空;非法重输
- 非 tty 回退:`--set` 或 getpass 简易询问

### 3.6 非交互修改

`api modify <name> --set model=gpt-5 --set base_url=https://...`;未知字段/非法值报错不保存;`--set key=xxx` 支持(明文命令行,文档允许)。

### 3.7 安全(本阶段)

- 显示脱敏:密钥 `前4 + **** + 后4`(长度≤8 时显示 `****`)
- 静默输入:prompt_toolkit `password=True`;非 tty 回退 `getpass`
- 存储仍明文(加密暂缓)

### 3.8 兼容性

- 旧位置参数 `api add <name> <base_url> <model> [api_key]` 保留,输出弃用警告并建议命名参数
- 现有测试同步更新;`list_connections` 不变

## 4. 错误处理

| 场景 | 处理 |
|---|---|
| 未知选项 `--xxx` | `ValueError`,提示"未知选项" |
| add 已存在 | 报错"连接已存在,使用 api modify",不覆盖 |
| del 确认拒绝 | 取消,不删除 |
| pull/sync 网络/认证/格式错误 | 复用 `ApiError` 分类,明确消息 |
| modify 非法 URL/空字段 | 重输,不保存 |
| modify Ctrl+X | 放弃修改,数据不变 |

## 5. 测试策略

| 测试 | 覆盖 |
|---|---|
| `test_args.py`(新增) | parse_args:命名参数/无值 flag/位置参数/未知选项 ValueError |
| `test_client.py`(扩展) | list_models 成功/401/格式异常(本地假服务器) |
| `test_store.py`(扩展) | last_tested 字段读写 |
| `test_shell.py`(重构) | add 已存在报错/del 确认/get 脱敏/modify --set/pull/sync(假服务器) |

## 6. 文件清单

```
src/rp_agent/api/args.py        # 新增:参数解析器
src/rp_agent/api/models.py      # 修改:last_tested 字段
src/rp_agent/api/store.py       # 修改:last_tested 读写
src/rp_agent/api/client.py      # 修改:list_models
src/rp_agent/shell.py           # 修改:_cmd_api 重构 + modify 交互
src/rp_agent/help_data.py       # 修改:api 命令帮助更新
tests/test_args.py              # 新增
tests/test_client.py            # 修改
tests/test_store.py             # 修改
tests/test_shell.py             # 修改
```

## 7. 兼容性

- 现有 69 项测试:test_shell 的 api 相关测试重构更新,其余保持
- 不新增依赖(prompt_toolkit 已引入);`uv.lock` 不变

## 8. 未来扩展点(记录,不在本阶段)

- 密钥加密存储(AES-256/keyring)
- 日志文件 `~/.rp-agent/logs/api.log`
- 新字段(headers/timeout 等)经 `--set` 扩展
