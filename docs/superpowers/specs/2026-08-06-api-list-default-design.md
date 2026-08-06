# api list 显示默认连接标记 — 设计文档

- 日期:2026-08-06
- 分支:`feat/api-list-default`
- 状态:已获用户确认(默认含义、显示形式、方案、边界、测试)

## 背景与目标

`api list` 目前只列出连接名(普通视图)或 tab 分隔字段(verbose 视图),
不标识当前正在使用的 API。用户希望列表明确显示全局默认连接
(`api use <name>` 设置,持久化于 `default_connection.json`)。

目标:`api list` 对默认连接显示 `*` 标记 + 黄色高亮,一眼识别
"当前正在使用的 API"。

## 已确认决策

- **默认指什么:** 全局默认连接(`api use` 设置),非会话连接(`api set`)
- **显示形式:** 星号后缀 `name *`,默认连接名字+星号整段黄色高亮(term.yellow)
- **实现方案:** 方案 B —— store 层新增轻量 `get_default_name()`,shell 调用
- **轻量查询哲学:** 与 `connection_exists` 一致,只读配置文件名/字段,
  不加载连接、不打日志;避免默认连接指向已删除连接时触发
  `json_read` 的误导性 WARNING(上一轮已修复同类问题)

## 架构

### store 层(`src/rp_agent/api/store.py`)

新增 `get_default_name() -> str | None`:

```python
def get_default_name() -> str | None:
    """当前默认连接名:仅读 default_connection.json 的 name 字段,不加载连接。"""
    ensure_dirs()
    path = _default_conn_path()
    if not path.exists():
        return None  # 未设置默认连接是常态,不告警
    data = json_read(path)
    if not isinstance(data, dict):
        return None
    name = str(data.get("name", ""))
    return name or None
```

重构 `get_default_connection()` 复用它(DRY):

```python
def get_default_connection() -> ApiConnection | None:
    name = get_default_name()
    return get_connection(name) if name else None
```

### shell 层(`src/rp_agent/shell.py` 的 `_api_list`)

- 开头取 `default_name = get_default_name()`(新增 import)
- 普通视图:默认连接 `print(f"  {yellow(c.name + ' *')}")`,非默认维持
  `print(f"  {c.name}")`
- verbose 视图:默认连接的 name 列同样加 `*` 与黄色高亮,其余列不变
- 无默认连接 → 全部无星号;默认指向已删除连接 → 该名字不在列表,
  无标记、不告警

### help 文案(`src/rp_agent/help_data.py`)

`api list` 描述补充:"默认连接以 * 标记"。

## 边界与错误处理

- 未设置默认连接:`get_default_name()` 返回 None,列表无星号
- 默认指向已删除连接:名字不在列表,无标记、无 WARNING
- 配置文件损坏(json_read 返回 None):视为无默认,不崩溃

## 测试(测试驱动)

### `tests/test_store.py`

- `get_default_name` roundtrip:set_default_connection("d") 后返回 "d"
- 未设置 → None
- 空名 → None
- 损坏 JSON → None

### `tests/test_shell.py`

| 用例 | 期望 |
|---|---|
| 设默认后 `api list` | 输出含 `d *`(文本断言,不含颜色码) |
| 未设默认 `api list` | 无 `*` |
| verbose `api list -v` | 默认行含 `d *` |
| 默认指向已删除连接 | 无星号且 caplog 无"读取 JSON 失败" |
| 非默认连接 | 无星号 |

## 明确不做(范围外)

- 不改 `api use` / `set_default_connection` 行为
- 不显示会话级连接(`api set`)
- 不做排序、筛选等无关改动
