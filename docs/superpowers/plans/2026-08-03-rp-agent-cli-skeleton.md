# rp-agent CLI 骨架实施计划(第一阶段)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 搭建 `rp-agent` 的可运行 CLI 骨架:Typer 入口 + 配置 + 标准库 logging + BaseTool 基类 + 提示词资源目录,配齐 pytest 测试与 git,全部由 UV 管理。

**Architecture:** src layout 单包 `rp_agent`;命令入口 `cli.py` → 加载配置 `config.py` → 初始化日志 `logging_setup.py`;`tools/`(能力层,含 `base/` 基类与 `mcp/` 占位)、`prompts/`(提示词资源)、`core/`(业务占位)按属性分目录。TDD,每任务独立可测、独立提交。

**Tech Stack:** Python 3.14(>=3.14)、UV 包管理、Typer CLI、标准库 `logging`(零额外依赖)、pytest。

## Global Constraints

- Python 版本必须 >= 3.14(当前环境 3.14.6);`requires-python = ">=3.14"`
- 依赖管理/虚拟环境/运行一律用 UV:`uv lock`、`uv sync`、`uv add`、`uv run`;锁文件 `uv.lock` 必须存在并提交
- CLI 框架只用 Typer;日志只用标准库 `logging`(禁止引入 loguru 等第三方日志库)
- 本阶段不引入 ruff/mypy 等代码质量工具
- 所有代码位于 `src/rp_agent/`(src layout),测试位于 `tests/`
- 工作分支 `feat/cli-skeleton`;每任务结束小步提交
- 测试命令统一 `uv run pytest <path> -v`(Windows 环境用 `uv run`,不用 `python3`)

---

### Task 1: 安装 uv 并初始化项目

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Generated: `uv.lock`、`.venv/`

**Interfaces:**
- Consumes: 无(项目根任务)
- Produces: `pyproject.toml`(含 `[project.scripts] rp-agent = "rp_agent.cli:app"`、`[dependency-groups] dev`)、可用的 `uv` 命令

- [ ] **Step 1: 安装 uv(当前环境未安装)**

```bash
winget install --id=astral-sh.uv -e
# 新终端验证;若当前 bash 会话找不到 uv,刷新 PATH 再验证:
export PATH="$PATH:$LOCALAPPDATA/Microsoft/WinGet/Links"
uv --version
```
Expected: 输出 uv 版本号(如 `uv 0.x.x`)。若 winget 失败,备选 `python -m pip install uv`,之后用 `python -m uv` 代替 `uv`。

- [ ] **Step 2: 写 `pyproject.toml`(完整内容)**

```toml
[project]
name = "rp-agent"
version = "0.1.0"
description = "AI 角色扮演 agent 平台(长期愿景:取代 SillyTavern),当前为 CLI 骨架阶段"
readme = "README.md"
requires-python = ">=3.14"
dependencies = [
    "typer>=0.15",
]

[project.scripts]
rp-agent = "rp_agent.cli:app"

[dependency-groups]
dev = [
    "pytest>=8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/rp_agent"]
```

- [ ] **Step 3: 写 `.gitignore`(完整内容)**

```gitignore
# uv / 虚拟环境
.venv/

# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/

# 编辑器
.idea/
.vscode/
```

- [ ] **Step 4: 写 `README.md`(完整内容)**

```markdown
# rp-agent

AI 角色扮演 agent 平台(长期愿景:取代 SillyTavern 的本地独立工具)。
当前为第一阶段:CLI 骨架。

## 开发环境

- Python >= 3.14
- UV 包管理

## 快速开始

\`\`\`bash
uv sync
uv run rp-agent --version
uv run rp-agent hello
uv run pytest
\`\`\`
```

- [ ] **Step 5: 生成锁文件与虚拟环境并验证**

```bash
uv lock
uv sync
uv run python -c "import typer; print(typer.__version__)"
uv run pytest --version
```
Expected: 均成功输出版本号;`uv.lock` 文件生成。

- [ ] **Step 6: 提交**

```bash
git add pyproject.toml uv.lock .gitignore README.md
git commit -m "chore: uv 初始化 rp-agent 项目(pyproject/.gitignore/README)"
```
注意:`.venv/` 已被 gitignore,不要提交。

---

### Task 2: 配置模块 `config.py`

**Files:**
- Create: `src/rp_agent/config.py`
- Create: `src/rp_agent/__init__.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `AppConfig`(dataclass):字段 `log_level: str = "INFO"`
  - `get_config(force_reload: bool = False) -> AppConfig`:模块级单例;`force_reload=True` 时重新从环境变量读取;读取 `RP_AGENT_LOG_LEVEL`(默认 `"INFO"`)

- [ ] **Step 1: 写失败的测试 `tests/test_config.py`**

```python
from rp_agent.config import get_config


def test_default_log_level():
    assert get_config(force_reload=True).log_level == "INFO"


def test_env_override(monkeypatch):
    monkeypatch.setenv("RP_AGENT_LOG_LEVEL", "DEBUG")
    assert get_config(force_reload=True).log_level == "DEBUG"


def test_singleton():
    assert get_config() is get_config()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_config.py -v
```
Expected: FAIL(`ModuleNotFoundError: No module named 'rp_agent'`)

- [ ] **Step 3: 写 `src/rp_agent/__init__.py` 与 `src/rp_agent/config.py`**

`src/rp_agent/__init__.py`:
```python
__version__ = "0.1.0"
```

`src/rp_agent/config.py`:
```python
"""全局配置:从环境变量读取,模块级单例。"""
from __future__ import annotations

import os
from dataclasses import dataclass

DEFAULT_LOG_LEVEL = "INFO"
ENV_LOG_LEVEL = "RP_AGENT_LOG_LEVEL"


@dataclass
class AppConfig:
    """应用配置。骨架阶段仅含日志级别,后续按需扩展字段。"""

    log_level: str = DEFAULT_LOG_LEVEL


_config: AppConfig | None = None


def get_config(force_reload: bool = False) -> AppConfig:
    """返回全局配置单例。

    force_reload=True 时忽略缓存,重新从环境变量构造(用于测试与运行时覆盖)。
    """
    global _config
    if _config is None or force_reload:
        _config = AppConfig(
            log_level=os.environ.get(ENV_LOG_LEVEL, DEFAULT_LOG_LEVEL),
        )
    return _config
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_config.py -v
```
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/__init__.py src/rp_agent/config.py tests/test_config.py
git commit -m "feat: 配置模块 AppConfig 与 get_config 单例"
```

---

### Task 3: 日志模块 `logging_setup.py`

**Files:**
- Create: `src/rp_agent/logging_setup.py`
- Test: `tests/test_logging.py`

**Interfaces:**
- Consumes: 无(仅标准库)
- Produces: `setup_logging(level: str = "INFO") -> None`:初始化 `rp_agent` logger(级别、stderr handler、固定格式);幂等(重复调用不叠加 handler);`propagate = False`

- [ ] **Step 1: 写失败的测试 `tests/test_logging.py`**

```python
import logging

from rp_agent.logging_setup import setup_logging


def test_log_to_stderr(capsys):
    setup_logging("INFO")
    logging.getLogger("rp_agent").info("hello-log")
    captured = capsys.readouterr()
    assert "hello-log" in captured.err
    assert captured.out == ""


def test_setup_idempotent():
    setup_logging("INFO")
    setup_logging("INFO")  # 不应抛错、不应叠加 handler
    logger = logging.getLogger("rp_agent")
    assert len(logger.handlers) == 1
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_logging.py -v
```
Expected: FAIL(`ModuleNotFoundError: No module named 'rp_agent.logging_setup'`)

- [ ] **Step 3: 写 `src/rp_agent/logging_setup.py`**

```python
"""日志初始化:标准库 logging,输出到 stderr,格式固定。"""
from __future__ import annotations

import logging
import sys

LOGGER_NAME = "rp_agent"
_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging(level: str = "INFO") -> None:
    """初始化 rp_agent 根 logger。幂等:已存在 handler 时不重复添加。"""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level.upper())
    logger.propagate = False
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_logging.py -v
```
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/logging_setup.py tests/test_logging.py
git commit -m "feat: 标准库 logging 初始化(setup_logging, stderr 输出)"
```

---

### Task 4: CLI 入口 `cli.py` + `__main__.py`

**Files:**
- Create: `src/rp_agent/cli.py`
- Create: `src/rp_agent/__main__.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes:
  - `from rp_agent import __version__`(Task 2 已建)
  - `get_config`、`AppConfig.log_level`(Task 2)
  - `setup_logging`(Task 3)
- Produces:
  - `app`:Typer 实例(`name="rp-agent"`、`no_args_is_help=True`)
  - `--version`/`-V` 选项(eager callback,输出 `rp-agent <__version__>` 后退出)
  - `hello` 命令:输出问候 + 当前 `cfg.log_level`,并写一条 INFO 日志
  - `python -m rp_agent` 可运行

- [ ] **Step 1: 写失败的测试 `tests/test_cli.py`**

```python
from typer.testing import CliRunner

from rp_agent import __version__
from rp_agent.cli import app

runner = CliRunner()


def test_version_flag():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_hello_command():
    result = runner.invoke(app, ["hello"])
    assert result.exit_code == 0
    assert "rp-agent" in result.stdout


def test_no_args_shows_help():
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: FAIL(`ModuleNotFoundError: No module named 'rp_agent.cli'`)

- [ ] **Step 3: 写 `src/rp_agent/cli.py` 与 `src/rp_agent/__main__.py`**

`src/rp_agent/cli.py`:
```python
"""Typer CLI 入口:唯一命令注册点。未来子命令(chat/character/agent)在此注册。"""
from __future__ import annotations

import logging

import typer

from rp_agent import __version__
from rp_agent.config import get_config
from rp_agent.logging_setup import setup_logging

logger = logging.getLogger("rp_agent")

app = typer.Typer(
    name="rp-agent",
    help="AI 角色扮演 agent 平台(长期愿景:取代 SillyTavern)",
    no_args_is_help=True,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"rp-agent {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        "-V",
        is_eager=True,
        callback=_version_callback,
        help="显示版本并退出",
    ),
) -> None:
    """rp-agent 全局入口:初始化配置与日志。"""
    cfg = get_config()
    setup_logging(cfg.log_level)
    logger.debug("配置加载完成: log_level=%s", cfg.log_level)


@app.command()
def hello() -> None:
    """冒烟命令:验证 命令 → 配置 → 日志 全链路。"""
    cfg = get_config()
    typer.echo(f"你好!rp-agent 骨架已就绪,当前日志级别: {cfg.log_level}")
    logger.info("hello 命令执行完成")
```

`src/rp_agent/__main__.py`:
```python
from rp_agent.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_cli.py -v
```
Expected: 3 passed

- [ ] **Step 5: 手动冒烟验证两种入口**

```bash
uv run rp-agent --version
uv run python -m rp_agent hello
uv run rp-agent --help
```
Expected: 均正常输出;`--help` 显示 `hello` 子命令。

- [ ] **Step 6: 提交**

```bash
git add src/rp_agent/cli.py src/rp_agent/__main__.py tests/test_cli.py
git commit -m "feat: Typer CLI 入口(--version/hello)+ __main__ 支持"
```

---

### Task 5: 工具基类 `tools/base/tool.py` + 占位目录

**Files:**
- Create: `src/rp_agent/core/__init__.py`(占位)
- Create: `src/rp_agent/tools/__init__.py`(占位)
- Create: `src/rp_agent/tools/base/__init__.py`(占位)
- Create: `src/rp_agent/tools/base/tool.py`
- Create: `src/rp_agent/tools/mcp/__init__.py`(占位)
- Create: `src/rp_agent/prompts/__init__.py`(占位)
- Test: `tests/test_tools.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `BaseTool`(ABC):类属性 `name: str`、`description: str`;抽象方法 `run(self, **kwargs: object) -> str`
  - 占位 `__init__.py` 内容为 `"""<说明>"""` 单行 docstring,保证包结构真实存在

- [ ] **Step 1: 写失败的测试 `tests/test_tools.py`**

```python
import pytest

from rp_agent.tools.base.tool import BaseTool


def test_abstract_cannot_instantiate():
    with pytest.raises(TypeError):
        BaseTool()  # type: ignore[abstract]


def test_concrete_tool_run():
    class EchoTool(BaseTool):
        name = "echo"
        description = "回显输入文本"

        def run(self, **kwargs: object) -> str:
            return str(kwargs.get("text", ""))

    tool = EchoTool()
    assert tool.name == "echo"
    assert tool.description == "回显输入文本"
    assert tool.run(text="hi") == "hi"
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_tools.py -v
```
Expected: FAIL(`ModuleNotFoundError: No module named 'rp_agent.tools.base.tool'`)

- [ ] **Step 3: 创建占位 `__init__.py` 与 `src/rp_agent/tools/base/tool.py`**

占位 `__init__.py`(每个文件内容为其职责一行说明,例如):
```python
"""core: 核心业务逻辑(未来:对话引擎/角色卡引擎)。"""
```
- `src/rp_agent/core/__init__.py`、`src/rp_agent/tools/__init__.py`、`src/rp_agent/tools/base/__init__.py`、`src/rp_agent/tools/mcp/__init__.py`、`src/rp_agent/prompts/__init__.py` 均按此模式创建。

`src/rp_agent/tools/base/tool.py`:
```python
"""工具基类:所有工具(未来含 MCP 工具)的统一接口锚点。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseTool(ABC):
    """工具抽象基类。

    约定:子类必须定义 `name`/`description` 类属性并实现 `run()`。
    """

    name: str
    description: str

    @abstractmethod
    def run(self, **kwargs: object) -> str:
        """执行工具,返回结果文本。骨架阶段签名从简,后续按需演进。"""
        raise NotImplementedError
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_tools.py -v
```
Expected: 2 passed

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/core src/rp_agent/tools src/rp_agent/prompts tests/test_tools.py
git commit -m "feat: BaseTool 抽象基类 + tools/core/prompts 目录结构"
```

---

### Task 6: 提示词资源 `prompts/system/default.md`

**Files:**
- Create: `src/rp_agent/prompts/system/__init__.py`(占位)
- Create: `src/rp_agent/prompts/system/default.md`
- Test: `tests/test_prompts.py`

**Interfaces:**
- Consumes: 无
- Produces: `src/rp_agent/prompts/system/default.md`(非空 Markdown 资源文件,提示词目录的落地锚点)

- [ ] **Step 1: 写失败的测试 `tests/test_prompts.py`**

```python
from pathlib import Path

SYSTEM_DIR = (
    Path(__file__).resolve().parents[1]
    / "src" / "rp_agent" / "prompts" / "system"
)


def test_default_prompt_exists_and_nonempty():
    prompt_file = SYSTEM_DIR / "default.md"
    assert prompt_file.exists()
    assert prompt_file.read_text(encoding="utf-8").strip()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_prompts.py -v
```
Expected: FAIL(`assert ... exists()` 为 False)

- [ ] **Step 3: 创建占位 `__init__.py` 与 `default.md`**

`src/rp_agent/prompts/system/__init__.py`:
```python
"""prompts.system: system prompt 模板资源。"""
```

`src/rp_agent/prompts/system/default.md`:
```markdown
# System Prompt(默认)

你是 rp-agent,一个 AI 角色扮演助手。

本文件是提示词资源目录的落地锚点;后续版本将在此放置真正的
system prompt 模板(含 RP 预设、性格引导等)。
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_prompts.py -v
```
Expected: 1 passed

- [ ] **Step 5: 提交**

```bash
git add src/rp_agent/prompts tests/test_prompts.py
git commit -m "feat: prompts/system/default.md 提示词资源锚点"
```

---

### Task 7: 通用启动脚本

**Files:**
- Create: `start.bat`
- Create: `start.ps1`
- Create: `start.sh`
- Test: `tests/test_start_scripts.py`

**Interfaces:**
- Consumes: Task 1 产物(`uv` 可用、`pyproject.toml` 的 `[project.scripts] rp-agent`)
- Produces: 三个跨平台启动脚本 —— 检查 `uv` → `uv sync` 确保依赖 → 透传参数执行 `rp-agent` CLI

- [ ] **Step 1: 写失败的测试 `tests/test_start_scripts.py`**

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_start_scripts_exist_and_nonempty():
    for name in ("start.bat", "start.ps1", "start.sh"):
        script = ROOT / name
        assert script.exists(), f"缺少启动脚本 {name}"
        assert script.read_text(encoding="utf-8", errors="ignore").strip()
```

- [ ] **Step 2: 运行测试确认失败**

```bash
uv run pytest tests/test_start_scripts.py -v
```
Expected: FAIL(`AssertionError: 缺少启动脚本 start.bat`)

- [ ] **Step 3: 写三个启动脚本**

`start.bat`(Windows 批处理,双击可用,失败时 pause 防止闪退):
```bat
@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo [rp-agent] 未找到 uv,请先安装: winget install --id=astral-sh.uv -e
    pause
    exit /b 1
)

uv sync >nul
uv run rp-agent %*
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
```

`start.ps1`(PowerShell):
```powershell
# rp-agent 通用启动脚本(PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[rp-agent] 未找到 uv,请先安装: winget install --id=astral-sh.uv -e" -ForegroundColor Red
    exit 1
}

uv sync | Out-Null
uv run rp-agent @args
exit $LASTEXITCODE
```

`start.sh`(类 Unix shell):
```bash
#!/usr/bin/env bash
# rp-agent 通用启动脚本(类 Unix)
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "[rp-agent] 未找到 uv,请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

uv sync >/dev/null
exec uv run rp-agent "$@"
```

- [ ] **Step 4: 运行测试确认通过**

```bash
uv run pytest tests/test_start_scripts.py -v
```
Expected: 1 passed

- [ ] **Step 5: 手动冒烟(Windows bash 会话验证 start.sh 与 start.bat)**

```bash
./start.sh --version
cmd //c start.bat --version
```
Expected: 两条均输出 `rp-agent 0.1.0`。

- [ ] **Step 6: 标记 start.sh 可执行并提交**

```bash
git update-index --chmod=+x start.sh
git add start.bat start.ps1 start.sh tests/test_start_scripts.py
git commit -m "feat: 通用启动脚本 start.bat/start.ps1/start.sh"
```

---

### Task 8: 全量验证与收尾

**Files:**
- Modify: `README.md`(如需补充启动脚本用法)

**Interfaces:**
- Consumes: 全部 Task 1-7 产物
- Produces: 全绿测试套件 + 完整 git 历史

- [ ] **Step 1: 运行全量测试**

```bash
uv run pytest -v
```
Expected: 全部通过(3 + 2 + 3 + 2 + 1 + 1 = 12 passed)

- [ ] **Step 2: 全量冒烟**

```bash
uv run rp-agent --version
uv run rp-agent hello
uv run python -m rp_agent hello
./start.sh --version
```
Expected: 四条命令均正常输出。

- [ ] **Step 3: 确认工作树整洁并提交收尾**

```bash
git status --short
git add -A
git commit -m "chore: 第一阶段 CLI 骨架完成"
git log --oneline
```
Expected: `git log --oneline` 显示连续提交历史(Task 1-7)。

---

## 验收清单(对照 spec)

- [ ] `uv run rp-agent --version` 输出版本号 → spec §5.1
- [ ] `uv run rp-agent hello` 正常输出并写日志 → spec §5.1、§6
- [ ] `RP_AGENT_LOG_LEVEL` 环境变量可覆盖日志级别 → spec §5.2
- [ ] 日志输出到 stderr,格式含时间/级别/logger 名 → spec §5.3
- [ ] `BaseTool` 抽象基类可被继承并 run() → spec §5.4
- [ ] `prompts/system/default.md` 存在且非空 → spec §5.5
- [ ] 目录按属性划分:core/tools(base,mcp)/prompts(system) → spec §4
- [ ] `start.bat`/`start.ps1`/`start.sh` 三个启动脚本存在且可运行(用户补充要求)
- [ ] `uv.lock` 已提交,依赖由 UV 管理 → Global Constraints
- [ ] 全部测试通过(12 passed)→ spec §8
