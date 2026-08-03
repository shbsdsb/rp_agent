# AGENTS.md — rp-agent

AI 角色扮演 agent 平台(长期愿景:取代 SillyTavern 的本地独立工具)。当前:CLI 骨架 + 热重载 + 储存链路 + 交互 shell + API 连接链路。

## Project

- 技术栈:Python >= 3.14、UV 包管理、Typer CLI、prompt_toolkit(交互输入)、标准库 logging、pytest
- 入口:`src/rp_agent/cli.py`(Typer app);支持 `python -m rp_agent` 与 console script `rp-agent`
- 启动脚本:`start.bat` / `start.ps1` / `start.sh`(检查 uv → uv sync → 透传参数运行 CLI);`start_ps.bat`(Windows 双击最小化启动 PowerShell 运行 shell)
- 数据目录:`data/`(运行时数据,不入 git,统一走 `storage.py`);默认配置:`src/rp_agent/configs/app.json`

## Commands

```bash
uv sync                 # 安装依赖(首次/依赖变更后)
uv run rp-agent shell       # 进入交互式 shell(主入口)
uv run rp-agent --watch hello  # 开发热重载(.py 重启 / config 热生效)
uv run rp-agent --version   # 版本
uv run python -m rp_agent   # 模块方式运行
uv run pytest -v            # 跑全部测试
uv add <pkg>            # 添加依赖(必须用 uv;添加前用 ask 询问用户)
```

## Architecture

- `src/rp_agent/cli.py` — Typer 入口,唯一命令注册点;未来子命令(chat/character/agent)在此注册
- `src/rp_agent/shell.py` — 交互 REPL:`parse_line`/`run_shell`、`_COMMANDS` 命令表、`ShellLexer`(prompt_toolkit 实时着色:有效命令黄/有效参数亮天蓝/有效选项灰,其余白)、`_cmd_api` 命令集(list/get/add/del/test/pull/sync/modify + `api <name> -m` 等效)
- `src/rp_agent/api/` — API 连接链路:`models.py`(`ApiConnection` + `mask_key`)、`store.py`(data/api/ 持久化)、`client.py`(`chat`/`test_connection`/`list_models`,OpenAI 兼容 urllib)、`args.py`(参数解析,长/短选项)
- `src/rp_agent/storage.py` — data 目录管理/JSON 读写(原子)/`safe_path` 防穿越
- `src/rp_agent/watch.py` — `Watcher` mtime 轮询热重载(零依赖)
- `src/rp_agent/term.py` — ANSI 颜色(黄 bold/亮天蓝/灰);`src/rp_agent/help_data.py` — help 数据表单(`HELP_ENTRIES`/`find_entry`)
- `src/rp_agent/config.py` — `AppConfig` + 配置文件热重载(`configs/app.json`,env 覆盖);`logging_setup.py` — 标准库 logging 输出 stderr
- `src/rp_agent/tools/` — 工具系统:`base/tool.py`(`BaseTool`)、`mcp/`(占位);`prompts/` — 提示词资源;`core/` — 业务占位(未来对话/角色卡引擎)
- `tests/` — pytest,与模块一一对应(含 test_args/test_client/test_store/test_shell/test_shell_lexer 等)

## Conventions

- 依赖/虚拟环境/运行一律用 UV(`uv add`/`uv run`/`uv sync`),锁文件 `uv.lock` 必须提交;禁止 pip/venv/conda;Python 版本固定 >= 3.14
- 允许添加第三方依赖,但**添加前必须用 ask 询问用户**(如 prompt_toolkit);日志只用标准库 `logging`(禁止 loguru),输出 stderr
- 交互式 REPL 输入必须用 prompt_toolkit(`prompt`/`Lexer`/`Style`/`InMemoryHistory`),禁止裸 `input()`(仅非 tty 回退);注意 prompt_toolkit 无 `ansigray`,灰色用 `ansibrightblack`
- src layout,目录按属性划分;测试驱动(先写 pytest 测试验证失败再实现)
- 新工具类继承 `tools/base/tool.py` 的 `BaseTool`;data 读写统一走 `storage.py`
- API 密钥:显示一律脱敏(`mask_key`),输入静默(prompt_toolkit `password=True` / 非 tty `getpass`);存储暂为明文
- Git:开发在 `feat/*` 或 `fix/*` 分支,小步提交,完成后合并到 `main`;不直接提交到 main
- 分支收尾:仍需用户确认,但**不用 ask 工具**,改为普通文本提问获取确认;用户确认后再合并
- Windows 注意:cmd/powershell 按系统代码页解析 bat,启动脚本内保持 ASCII 消息;bat 须 CRLF 换行(LF 会解析错乱);路径尾部反斜杠与引号组合会转义(用 `%~dp0.` 规避)

## Notes

(留空,后续补充)
