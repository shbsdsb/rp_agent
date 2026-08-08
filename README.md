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

## 配置

- 配置文件:`src/rp_agent/configs/app.json`(JSON),优先级:**环境变量 > 配置文件 > 默认值**
- shell 内 `reload` 命令可热重载配置;`config timeout <秒>` 可修改全局超时

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

交互终端中,输入命令实时着色:命令黄色、参数亮天蓝、`--选项` 灰色;支持方向键历史。

## API 连接

连接配置存于 `data/api/<name>.json`(明文 api_key,不入 git):

```bash
uv run rp-agent shell
rp-agent> api add openai https://api.openai.com/v1 gpt-4o sk-xxx
rp-agent> api test openai
```

shell 命令:`api list [-v] [--filter k=v]` / `api get <name>` /
`api add --name N --url U --key K [--model M] [--modify] [--pull]` /
`api del <name> [-f]` / `api test <name> [--timeout N]` /
`api pull <name> [--set-default]` / `api sync <name> [--set-default]` /
`api modify <name> [--set field=value]`(交互模式支持 Ctrl+O 保存/Ctrl+X 放弃,/url /key /model 跳转)。
密钥显示脱敏;`api test`/`sync` 记录 `last_tested`。
