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
