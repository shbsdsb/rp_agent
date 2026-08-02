# rp-agent

AI 角色扮演 agent 平台(长期愿景:取代 SillyTavern 的本地独立工具)。
当前为第一阶段:CLI 骨架。

## 开发环境

- Python >= 3.14
- UV 包管理

## 快速开始

```bash
uv sync
uv run rp-agent --version
uv run rp-agent hello
uv run pytest
```

## 热重载

- 配置文件:`src/rp_agent/configs/app.json`(JSON),优先级:**环境变量 > 配置文件 > 默认值**
- 开发热重载:

```bash
uv run rp-agent --watch hello
```

代码变更(.py)自动重启;配置文件变更热生效,无需重启。

## 数据存储

项目根 `data/` 目录(不入 git),运行时数据:

- `characters/` — 角色卡
- `chats/` — 聊天记录
- `presets/` — RP 预设
- `api/` — API 连接配置

所有 data 读写统一走 `src/rp_agent/storage.py`(`json_read`/`json_write`/`safe_path`)。

## 交互式 Shell

```bash
uv run rp-agent shell
```

内置命令:`help`(帮助)、`config`(查看配置)、`reload`(热重载配置)、
`storage`(查看 data 目录)、`hello`(冒烟)、`history`(输入历史)、`exit`/`quit`(退出)。

输入 `<命令> --help`(如 `config --help`)查看该命令详细用法与参数。

## API 连接

连接配置存于 `data/api/<name>.json`(明文 api_key,不入 git):

```bash
uv run rp-agent shell
rp-agent> api add openai https://api.openai.com/v1 gpt-4o sk-xxx
rp-agent> api test openai
```

shell 命令:`api list` / `api get <name>` / `api add <name> <base_url> <model> [api_key]` / `api del <name>` / `api test <name>`(OpenAI 兼容)。
