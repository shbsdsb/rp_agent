# rp-agent CLI 骨架设计(第一阶段)

日期:2026-08-03
状态:已获用户口头批准(含日志改用标准库 `logging` 的修订)

## 1. 背景与愿景

`rp-agent` 是一个本地独立的 CLI agent 项目,长期愿景是构建一个能取代 SillyTavern 的 AI 角色扮演平台,包含两个工作模式:

1. **对话模式**:正常的 AI 对话交流 / AI RP 聊天(加载角色卡、多轮对话、上下文管理)
2. **Agent 模式**:特定领域自动化(自动生成/优化角色卡、调优预设、批量处理等)

长期子系统分解(背景参考,不在本阶段范围):

| 子系统 | 说明 |
|---|---|
| A. 角色卡引擎 | CCv3 规范解析/生成,PNG 内嵌 JSON,角色卡编辑与校验 |
| B. RP 聊天内核 | LLM 后端接入、预设/提示词管理、上下文窗口与记忆、流式输出 |
| C. Agent 自动化层 | 工具调用,自动生成/优化角色卡、调优预设 |
| D. 存储与配置 | 角色卡库、聊天记录、设置持久化 |
| E. UI(未来) | 网页界面取代 SillyTavern |

**本阶段(第一天)范围**:搭建可运行的 CLI 项目骨架 + 基础开发设施,并为上述子系统预留按属性划分的目录落位。

## 2. 目标与范围

### 做
- 可运行的 Typer CLI 骨架(`--version` + `hello` 冒烟命令)
- 按属性划分的目录结构(`core/`、`tools/`、`prompts/`)
- 基础开发设施:git 初始化、pytest 测试、标准库 `logging` 结构化日志、配置加载
- 两个"真实锚点"文件,验证结构可扩展可测试:`tools/base/tool.py`(BaseTool 抽象基类)、`prompts/system/default.md`(最小 system prompt 示例)

### 不做(留给后续阶段)
- 对话引擎、角色卡引擎、MCP 实际集成、LLM 后端接入、UI

## 3. 技术栈

| 项 | 选择 |
|---|---|
| 语言/版本 | Python 3.14(`requires-python = ">=3.14"`,当前环境 3.14.6) |
| 包管理 | UV(`uv venv` / `uv add` / `uv run` / `uv.lock`) |
| CLI 框架 | Typer |
| 日志 | 标准库 `logging`(零依赖;结构化:JSON/键值格式,输出到 stderr) |
| 测试 | pytest |
| 代码质量 | 本阶段不引入 ruff/mypy(用户明确选择,YAGNI) |

## 4. 目录结构(按属性划分)

```
rp-agent/
├── pyproject.toml              # 元数据 + 依赖(uv 管理)
├── uv.lock                     # 依赖锁文件
├── .gitignore
├── README.md
├── docs/superpowers/specs/     # 设计文档
├── src/
│   └── rp_agent/
│       ├── __init__.py         # __version__
│       ├── __main__.py         # 支持 python -m rp_agent
│       ├── cli.py              # Typer 入口,唯一命令注册点
│       ├── config.py           # AppConfig dataclass,环境变量可覆盖
│       ├── logging_setup.py    # 标准库 logging 初始化(级别/格式/stderr)
│       ├── core/               # 核心业务逻辑(未来:对话/角色卡引擎)
│       │   └── __init__.py     # 本阶段仅占位
│       ├── tools/              # 工具系统:agent 的能力层
│       │   ├── __init__.py
│       │   ├── base/           # 工具基类与抽象
│       │   │   ├── __init__.py
│       │   │   └── tool.py     # BaseTool 抽象基类(本阶段落地)
│       │   └── mcp/            # MCP(Model Context Protocol)集成
│       │       └── __init__.py # 本阶段仅占位
│       └── prompts/            # 提示词资源:按类型分目录
│           ├── __init__.py
│           └── system/
│               ├── __init__.py
│               └── default.md  # 最小 system prompt 示例(本阶段落地)
└── tests/
    ├── __init__.py
    ├── test_cli.py             # CLI 冒烟测试
    ├── test_logging.py         # 日志测试
    └── test_tools.py           # BaseTool 基类测试
```

设计原则:
- **按属性分**,不按功能分:`tools/`(能力)、`prompts/`(提示词资源)、`core/`(业务)、`config.py`(配置)各归其位
- `tools/` 下按工具类型再分:`base/` 基类、`mcp/` 集成;未来加 `http/`、`shell/` 等类型即同级加目录
- `prompts/` 下按提示词用途再分:`system/` 先落地;未来加 `user/`、`character/` 等
- 目录按"真实存在、可测试"落地,不用纯空壳堆砌(仅 `core/`、`tools/mcp/` 放 `__init__.py` 占位)

## 5. 组件规格

### 5.1 `cli.py` — Typer 入口
- `app = typer.Typer(...)`,`app.version` 或 `--version` 选项输出版本号
- 子命令:`hello`(冒烟命令,输出问候 + 当前配置的日志级别,验证命令→配置→日志全链路)
- 唯一命令注册点;未来子命令(chat/character/agent)在此注册

### 5.2 `config.py` — 配置
- `AppConfig` dataclass:字段如 `log_level`(默认 INFO)
- 从环境变量读取(如 `RP_AGENT_LOG_LEVEL`),带默认值
- 提供 `get_config() -> AppConfig`:首次调用构造并缓存,后续返回同一实例(模块级单例,幂等且便于测试重置)

### 5.3 `logging_setup.py` — 日志
- 标准库 `logging`,根 logger 命名空间 `rp_agent`
- 级别由配置控制,格式含时间/级别/logger 名/消息
- 输出到 stderr(不污染 stdout,便于 CLI 管道输出)
- 提供 `setup_logging(level)` 函数,幂等

### 5.4 `tools/base/tool.py` — BaseTool 抽象基类
- 属性:`name`(str)、`description`(str)
- 抽象方法:`run(self, **kwargs) -> str`:接受任意关键字参数,返回工具执行结果文本。骨架阶段从简,后续按需演进签名
- 目的:为未来 MCP 工具/自定义工具提供统一接口锚点

### 5.5 `prompts/system/default.md` — 最小 system prompt 示例
- 最小可用文本,作为提示词资源目录的落地锚点

### 5.6 `__main__.py` / `__init__.py`
- `__main__.py`:`from .cli import app; app()` 支持 `python -m rp_agent`
- `__init__.py`:`__version__ = "0.1.0"`

## 6. 数据流

```
用户命令 → cli.py → setup_logging(config) + 加载配置
        → 执行命令 → 日志输出到 stderr
未来扩展:命令 → core → tools(mcp 等) → LLM 后端
```

## 7. 错误处理

- 未捕获异常 → logger.exception 记录 traceback,CLI 以非零退出码结束(Typer 默认行为 + 显式包装)
- 参数错误 → Typer 自带 `--help` / 参数校验

## 8. 测试策略

| 测试 | 覆盖 |
|---|---|
| `test_cli.py` | Typer `CliRunner` 验证 `--version` 输出、`hello` 退出码 0 |
| `test_logging.py` | `setup_logging` 幂等、日志写入 stderr(capsys) |
| `test_tools.py` | 定义 `BaseTool` 子类,验证实例化与 `run()` 调用 |

## 9. 交付动作

1. `uv init` 生成 `pyproject.toml`,配置依赖:typer(运行时);dev:pytest(日志用标准库 `logging`,无额外依赖)
2. 按第 4 节结构创建全部文件
3. `uv run pytest` 全部通过
4. `git init` + 首次提交(含设计文档)
5. 设计文档落位 `docs/superpowers/specs/2026-08-03-rp-agent-cli-skeleton-design.md`

## 10. 未来扩展点(记录,不在本阶段实现)

- `tools/mcp/`:MCP 客户端/服务器集成
- `core/`:对话引擎、角色卡引擎(CCv3)
- `prompts/`:user/character 等提示词类型
- 配置持久化(配置文件而非仅环境变量)
- 依赖新增时用 `uv add`,严格遵循 `uv.lock`
