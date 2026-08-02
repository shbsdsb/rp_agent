# 热重载功能设计(配置文件 + `--watch` 开发热重载)

日期:2026-08-03
状态:已获用户口头批准

## 1. 背景

`rp-agent` 已完成第一阶段 CLI 骨架(配置/日志/CLI/工具基类/提示词资源)。本阶段添加两项热重载能力:

1. **配置热重载**:新增 JSON 配置文件,运行中配置变化**不重启进程**即热生效
2. **开发热重载(watch)**:`--watch` 通用选项,监控代码变化自动重启,提升开发效率

## 2. 目标与范围

### 做
- 新增 `src/rp_agent/configs/` 目录(与 tools/prompts/core 平级),存放 JSON 配置文件
- `config.py` 扩展:从文件加载配置,优先级 **环境变量 > 配置文件 > 默认值**,新增 `reload_config()` 变化检测
- 新增 `src/rp_agent/watch.py`:`Watcher` 轮询(mtime)监控,零依赖
- `cli.py` 扩展:`--watch` 全局选项,子进程管理
- 分工:**.py 变更 → 重启子进程**; **configs/*.json 变更 → 不重启,热生效**(调用 `reload_config()` 并打印日志)

### 不做
- 不引入 watchdog 等第三方依赖(保持仅依赖 typer)
- 不做未来 chat/character 会话(本阶段只搭机制与验证)
- 不做配置文件 schema 校验框架(骨架阶段仅合并 dict)

## 3. 技术方案

### 3.1 配置文件

`src/rp_agent/configs/app.json`(默认配置,包内资源):
```json
{ "log_level": "INFO" }
```
- 路径:`Path(__file__).parent / "configs" / "app.json"`
- 未来字段直接加键,未知键忽略(不报错,便于向后兼容)

### 3.2 `config.py` 扩展

| API | 语义 |
|---|---|
| `DEFAULT_CONFIG_PATH: Path` | 包内 configs/app.json 路径 |
| `load_config_file(path: Path | None = None) -> dict[str, Any]` | 读 JSON;缺失/损坏返回 `{}` 并 `logger.warning`,不崩溃 |
| `reload_config() -> bool` | 重新加载(文件 + env),更新单例;返回**配置是否发生变化**(供 watch 判断是否需要热生效动作) |
| `get_config(force_reload: bool = False) -> AppConfig` | 语义不变,向后兼容;`force_reload=True` 时也走文件+env 合并 |

合并优先级:**env(`RP_AGENT_LOG_LEVEL`)> 文件(`log_level`)> 默认(`"INFO"`)**。

### 3.3 `watch.py` — Watcher

```python
class Watcher:
    def __init__(self, py_dirs: Sequence[Path], config_files: Sequence[Path],
                 on_restart: Callable[[], None], on_reload: Callable[[], None],
                 interval: float = 0.5) -> None: ...
    def run(self) -> None: ...        # 阻塞轮询,直到 stop 或 KeyboardInterrupt
    def stop(self) -> None: ...       # 优雅停止
```
- 轮询 mtime 快照,变化即触发对应回调(去抖:同一次扫描内只触发一次)
- 监控范围:`src/rp_agent/**/*.py`(递归)+ `configs/*.json`
- 零依赖,标准库 `time`/`pathlib`

### 3.4 `cli.py` 扩展

- 全局选项 `--watch`(`rp-agent --watch hello` 等,通用)
- watch 模式行为(在 `main` callback 中拦截):
  1. 剥离 `--watch` 后,spawn 子进程执行原命令:`[sys.executable, "-m", "rp_agent", *剩余参数]`(跨平台,不依赖 uv)
  2. `.py` 变更 → kill 旧子进程 → 重新 spawn,日志:`[watch] 检测到变更,重启…`
  3. `configs/*.json` 变更 → 不重启,`reload_config()` 热生效,日志:`[watch] 配置已热重载: log_level=…`
  4. Ctrl+C → kill 子进程,正常退出

## 4. 目录与文件清单

```
src/rp_agent/
├── config.py        # 修改:文件加载 + 优先级合并 + reload_config()
├── watch.py         # 新增:Watcher(轮询 + 回调分发)
├── cli.py           # 修改:--watch 全局选项 + 子进程管理
└── configs/
    ├── __init__.py  # 新增(占位,包内资源目录)
    └── app.json     # 新增(默认配置文件)
tests/
├── test_config.py   # 修改:文件加载/优先级/reload 变化检测
├── test_watch.py    # 新增:Watcher mtime 触发回调(临时目录)
└── test_cli.py      # 修改:--watch 参数解析
```

## 5. 错误处理

| 场景 | 处理 |
|---|---|
| app.json 缺失 / JSON 损坏 | 回退默认值 + `logger.warning`,不崩溃 |
| watch 子进程崩溃/退出 | 打印退出码,等待下次变更(不自动无限重启) |
| Ctrl+C | 终止子进程,正常退出(exit 0) |
| 配置文件热重载失败(如删文件) | `reload_config()` 回退默认并告警,不退出 |

## 6. 测试策略

| 测试 | 覆盖 |
|---|---|
| `test_config.py` 扩展 | JSON 加载、env 覆盖文件、文件缺失回退、`reload_config()` 变更检测(改文件→True,未改→False) |
| `test_watch.py`(新增) | Watcher 轮询临时目录:改 .py 触发 restart 回调、改 .json 触发 reload 回调 |
| `test_cli.py` 扩展 | `--watch` 选项解析;watch 分支正确剥离参数并进入 Watcher |

## 7. 兼容性

- `get_config()` / `force_reload` 语义向后兼容,现有 12 项测试保持通过
- 日志仍为标准库 logging、输出 stderr
- 依赖不新增(watch 零依赖),`uv.lock` 不变

## 8. 未来扩展点(记录,不在本阶段)

- 配置 schema 校验、配置 diff 日志
- chat/character 会话中的热重载应用(加载角色卡/预设变化)
- watch 排除规则、防抖窗口调优
