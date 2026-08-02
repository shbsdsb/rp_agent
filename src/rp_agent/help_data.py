"""Shell 帮助数据表单(查询表单)。"""
from __future__ import annotations

HELP_ENTRIES: list[dict[str, object]] = [
    {
        "command": "help",
        "aliases": ["?"],
        "desc": "显示帮助(help | <命令> --help)",
        "usage": "help [命令]",
        "params": [("命令", "可选:查看指定命令的详细帮助")],
    },
    {
        "command": "config",
        "aliases": [],
        "desc": "显示当前配置",
        "usage": "config",
        "params": [],
    },
    {
        "command": "reload",
        "aliases": [],
        "desc": "热重载配置",
        "usage": "reload",
        "params": [],
    },
    {
        "command": "storage",
        "aliases": [],
        "desc": "列出 data 目录内容",
        "usage": "storage",
        "params": [],
    },
    {
        "command": "hello",
        "aliases": [],
        "desc": "冒烟命令",
        "usage": "hello",
        "params": [],
    },
    {
        "command": "history",
        "aliases": [],
        "desc": "显示输入历史",
        "usage": "history",
        "params": [],
    },
    {
        "command": "exit",
        "aliases": ["quit"],
        "desc": "退出 shell",
        "usage": "exit",
        "params": [],
    },
    {
        "command": "api",
        "aliases": [],
        "desc": "API 连接管理",
        "usage": "api <list|get|add|del|test> ...",
        "params": [
            ("list", "列出所有连接"),
            ("get <name>", "查看连接详情(密钥打码)"),
            ("add <name> <base_url> <model> [api_key]", "新增/覆盖连接"),
            ("del <name>", "删除连接"),
            ("test <name>", "真实调用验证连接"),
        ],
    },
]


def find_entry(command: str) -> dict[str, object] | None:
    """按命令名(含别名)查找帮助条目。"""
    for entry in HELP_ENTRIES:
        if command == entry["command"] or command in entry["aliases"]:
            return entry
    return None
