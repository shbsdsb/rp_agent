# API 连接管理命令集重构设计(修订版 v2)

日期:2026-08-03(修订 2026-08-04)
状态:**草案 v2,待用户确认**(已按审计报告修正)

## 1. 背景

现有 `api` 命令集(6 个子命令)功能简单。用户提供重构设计(本次命令.md)并经审计报告(2026-08-04)指正,本修订版修正:参数顺序、`--modify` 覆盖、`-m` 快捷、`--pull` 失败行为、短选项、`models_endpoint`、交互细节、原子性、脱敏边界、UTC 时间、测试方案等。

## 2. 目标与范围

### 做
- 新增 `api/args.py`:轻量参数解析器(长/短选项 + 位置参数)
- 命令集重构:list/get/add/del/test 升级 + 新增 pull/sync/modify
- `client.py` 新增 `list_models`(`GET {base_url}/{models_endpoint}`)
- `store.py`:`last_tested`(UTC ISO)字段
- modify 交互式编辑(nano 快捷键 + 底部提示栏)+ 非交互 `--set`(原子更新)
- 密钥脱敏(前4后4,长度≤8 显示 `****`)、静默输入

### 不做
- 不做密钥加密存储(暂缓);不做日志文件;不新增依赖(表格仍 tab 分隔)

## 3. 技术方案

### 3.1 `api/args.py` — 参数解析器

```python
# 短选项映射
_SHORT_OPTS = {"-v": "--verbose", "-f": "--force", "-m": "--modify", "-t": "--timeout"}
# -t/--timeout、--filter 等取值选项;无值选项集合
def parse_args(argv: list[str]) -> tuple[dict[str, str], list[str]]:
    """解析 --key value / --flag / -v 短选项 / 位置参数。

    - `--name value` → {"name": "value"};`--verbose` 无值 → {"verbose": ""}
    - 短选项经 _SHORT_OPTS 映射为长选项;`-t 5` → {"timeout": "5"}
    - `--filter model=gpt-4` 存入 {"filter": "model=gpt-4"}(值不允许空格;支持多次,按 AND 组合)
    - 未知选项(如 `--xxx`)抛 ValueError("未知选项: --xxx")
    - 其余为位置参数列表
    """
```
- 选项与位置参数可混用;`--key value` 形式的值不支持含空格(骨架阶段)

### 3.2 命令集总览

| 命令 | 行为 |
|---|---|
| `list` | 默认只显名称;`-v/--verbose` 表格(`名称\tBase URL\t模型\t最近测试`);`--filter k=v` 可多次,AND 组合 |
| `get <name>` | 显示字段;密钥脱敏前4后4;不存在报错 |
| `add` | 命名参数 `--name --url --key [--model]`;**已存在**:默认报错,加 `--modify/-m` 则用新参数覆盖(非交互);**位置简写**(新顺序)`add <name> <base_url> <api_key> [model]` + 弃用警告;可选 `--pull`:拉取模型,**失败仅警告仍保存** |
| `del <name>` | 二次确认 `y/N`;`-f/--force` 跳过 |
| `test <name> [-t/--timeout N]` | 探测连通性(默认超时 10s);成功更新 `last_tested`(UTC) |
| `pull` | `pull <name> [--set-default]` 或 `pull --url --key [-t]`(临时,请求前校验 URL);调 `GET {base_url}/{models_endpoint}` |
| `sync <name> [--set-default]` | 测试 → 拉取模型 → 打印;`--set-default` 直接设定第一模型并提示(无需确认) |
| `modify <name>` | 交互式(默认)或 `--set field=value`(可多次,原子更新);**`api <name> -m` 等价快捷方式** |

### 3.3 `client.py` 新增

```python
def list_models(conn: ApiConnection, timeout: float | None = None) -> list[str]:
    """GET {base_url}/{conn.models_endpoint},解析 data[].id;错误复用 ApiError 分类。"""
```

### 3.4 `store.py` / `models.py` 扩展

- `ApiConnection` 增加字段:
  - `models_endpoint: str = "/models"`(自定义模型列表端点,兼容非 OpenAI 服务)
  - `last_tested: str = ""`(**UTC ISO 时间**,`datetime.now(timezone.utc).isoformat()`,缺省空串)
- `save_connection`/`get_connection` 读写新字段(缺失默认)

### 3.5 脱敏规则(明确边界)

```python
def mask_key(key: str) -> str:
    """密钥脱敏:长度<=8 显示 ****;否则 前4 + **** + 后4。"""
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}****{key[-4:]}"
```

### 3.6 modify 交互式编辑(nano 风格)

- 子提示符 `rp-agent-modify-<name>>`;依次编辑 `Base URL → API Key(静默,password=True)→ Model`;回车保留原值
- **字段跳转**:每个字段提示输入时,检查输入是否以 `/` 开头(`/url`、`/key`、`/model`)→ 跳转到对应字段;未知 `/xxx` 提示
- **底部固定提示栏**(prompt_toolkit `bottom_toolbar`):
  ```
  ^O 保存  ^X 放弃  ^R 重置  ^G 帮助
  ```
  - `key_bindings`:`Ctrl+O` 保存退出;`Ctrl+X` 放弃退出;`Ctrl+R` 重置原值;`Ctrl+G` 帮助
- 校验:URL 以 http(s):// 开头、非空;非法重输
- **非 tty 回退**:`--set` 模式或 `getpass` 简易询问
- 实现:用 `prompt_toolkit.shortcuts.prompt` 的 `key_bindings` 参数 + `bottom_toolbar`(版本 3.0.53 支持)

### 3.7 非交互修改(原子性)

`api modify <name> --set model=gpt-5 --set base_url=https://...`:
1. **先验证全部字段**(URL 格式/非空/字段名已知),任一非法 → 报错,**不写入任何字段**
2. 全部合法后一次性 `save_connection` 更新存储
3. `--set key=xxx` 支持(明文命令行,文档允许)

### 3.8 安全(本阶段)

- 显示脱敏(3.5 规则);静默输入(prompt_toolkit `password=True` / 非 tty `getpass`)
- 存储仍明文(加密暂缓)

### 3.9 兼容性

- 旧位置参数 `add <name> <base_url> <model> [api_key]`(旧顺序)→ **弃用**:新顺序为 `add <name> <base_url> <api_key> [model]`;旧顺序无法兼容,直接按新顺序解析并在 help 注明;已存连接文件自动兼容(缺失字段取默认)
- 现有测试同步更新

## 4. 错误处理

| 场景 | 处理 |
|---|---|
| 未知选项/短选项 | `ValueError`,`_cmd_api` 统一捕获,输出友好错误(不堆栈) |
| add 已存在(无 --modify) | 报错"连接已存在,使用 api modify 或 add --modify 覆盖" |
| add --pull 失败 | **警告仍保存**(可后续 pull) |
| del 确认拒绝 | 取消,不删除 |
| pull/sync 网络/认证/格式错误 | 复用 `ApiError` 分类 |
| pull 临时模式 URL 非法 | 请求前校验,明确报错 |
| modify 非法 URL/空字段 | 重输,不保存 |
| modify --set 部分非法 | 全部验证后写入,原子性,不部分保存 |
| modify Ctrl+X | 放弃修改,数据不变 |

## 5. 测试策略

| 测试 | 覆盖 |
|---|---|
| `test_args.py`(新增) | 命名参数/无值 flag/短选项(-v/-f/-t)/位置参数/未知选项 ValueError/--filter 多次 |
| `test_client.py`(扩展) | list_models 成功/401/格式异常;自定义 models_endpoint;本地假服务器(含超时/连接拒绝) |
| `test_store.py`(扩展) | last_tested/models_endpoint 读写;旧文件兼容(缺失字段默认) |
| `test_shell.py`(重构) | add 已存在报错/add --modify 覆盖/add 新顺序位置参数+弃用警告/del 确认/get 脱敏(≤8 与长密钥)/modify --set 原子性(部分非法不写入)/pull/sync(假服务器) |
| modify 交互测试 | monkeypatch 模拟 prompt_toolkit 输入序列(Ctrl+O/X、/field 跳转);`_read_line` 注入机制复用 |

## 6. 文件清单

```
src/rp_agent/api/args.py        # 新增:参数解析器(含短选项映射)
src/rp_agent/api/models.py      # 修改:models_endpoint/last_tested 字段
src/rp_agent/api/store.py       # 修改:新字段读写
src/rp_agent/api/client.py      # 修改:list_models(可配端点)
src/rp_agent/shell.py           # 修改:_cmd_api 重构 + modify 交互 + 错误捕获
src/rp_agent/help_data.py       # 修改:api 命令帮助(命令表/用法/参数)
tests/test_args.py              # 新增
tests/test_client.py            # 修改
tests/test_store.py             # 修改
tests/test_shell.py             # 修改
```

## 7. 兼容性

- 现有 69 项测试:test_shell 的 api 相关测试重构更新;其余保持
- 不新增依赖(prompt_toolkit 已引入,版本 3.0.53 支持 key_bindings/bottom_toolbar);`uv.lock` 不变
- 已存连接文件向后兼容(新字段缺省)

## 8. 未来扩展点(记录,不在本阶段)

- 密钥加密存储(AES-256/keyring)
- 日志文件 `~/.rp-agent/logs/api.log`
- `--filter` 值含空格/引号语法;表格渲染库(texttable/prettytable)
- 默认超时进配置;更多新字段经 `--set` 扩展
