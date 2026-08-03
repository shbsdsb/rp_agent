# AGENTS.md — rp-agent

AI 角色扮演 agent 平台(长期愿景:取代 SillyTavern 的本地独立工具)。当前为 CLI 骨架阶段。

## Project

- 技术栈:Python >= 3.14、UV 包管理、Typer CLI、标准库 logging、pytest
- 入口:`src/rp_agent/cli.py`(Typer app);支持 `python -m rp_agent` 与 console script `rp-agent`
- 项目根启动脚本:`start.bat` / `start.ps1` / `start.sh`(检查 uv → uv sync → 透传参数运行 CLI)

## Commands

```bash
uv sync                 # 安装依赖(首次/依赖变更后)
uv run rp-agent --version   # 运行 CLI
uv run rp-agent hello       # 冒烟命令
uv run python -m rp_agent   # 模块方式运行
uv run pytest -v            # 跑全部测试
uv add <pkg>            # 添加依赖(必须用 uv,禁止 pip/venv)
```

## Architecture

- `src/rp_agent/cli.py` — Typer 入口,唯一命令注册点;未来子命令(chat/character/agent)在此注册
- `src/rp_agent/config.py` — `AppConfig` dataclass + `get_config()` 单例;`RP_AGENT_LOG_LEVEL` 环境变量覆盖
- `src/rp_agent/logging_setup.py` — 标准库 logging,输出 stderr,幂等
- `src/rp_agent/tools/` — 工具系统:`base/tool.py`(`BaseTool` 抽象基类)、`mcp/`(占位,未来 MCP 集成)
- `src/rp_agent/prompts/` — 提示词资源,按类型分目录:`system/default.md`
- `src/rp_agent/core/` — 业务逻辑占位(未来:对话引擎/角色卡引擎 CCv3)
- `tests/` — pytest 测试,与模块一一对应(test_cli/test_config/test_logging/test_tools/test_prompts/test_start_scripts)

## Conventions

- 依赖/虚拟环境/运行一律用 UV(`uv add`/`uv run`/`uv sync`),锁文件 `uv.lock` 必须提交;禁止 pip/venv/conda
- Python 版本固定 >= 3.14
- 日志只用标准库 `logging`(禁止第三方日志库如 loguru),输出 stderr
- src layout:所有代码在 `src/rp_agent/`,目录按属性划分(能力/资源/业务),新子模块同级加目录
- 测试驱动:新增功能先写 pytest 测试(用 `uv run pytest <file> -v` 验证失败再实现)
- 新工具类继承 `tools/base/tool.py` 的 `BaseTool`(name/description 类属性 + `run(**kwargs) -> str`)
- Git:开发在 `feat/*` 或 `fix/*` 分支,小步提交,完成后合并到 `main`;不直接提交到 main
- 分支收尾:仍需用户确认,但**不用 ask 工具**,改为普通文本提问获取确认(用户测试后可能需要更大输入框,避免 ask 弹窗干扰);用户确认后再合并
- Windows 注意:cmd/powershell 按系统代码页解析 bat,启动脚本内保持 ASCII 消息;路径尾部反斜杠与引号组合会转义(用 `%~dp0.` 规避)

## Notes

(留空,后续补充)
