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
        "desc": "API 连接管理(api list/get/add/del/test/pull/sync/modify)",
        "usage": "api <list|get|add|del|test|pull|sync|modify> ...",
        "params": [
            ("list [-v] [--filter k=v]", "列出连接(详细视图/筛选)"),
            ("get <name>", "查看连接详情(密钥脱敏)"),
            ("add --name N --url U --key K [--model M] [--modify] [--pull]", "新建/覆盖连接"),
            ("del <name> [-f]", "删除连接(默认二次确认)"),
            ("test <name> [--timeout N]", "测试连接连通性"),
            ("pull <name> [--set-default] | pull --url U --key K", "拉取模型列表"),
            ("sync <name> [--set-default]", "测试并拉取模型"),
            ("modify <name> [--set field=value ...]", "交互或非交互修改"),
        ],
    },
]


def find_entry(command: str) -> dict[str, object] | None:
    """按命令名(含别名)查找帮助条目。"""
    for entry in HELP_ENTRIES:
        if command == entry["command"] or command in entry["aliases"]:
            return entry
    return None
