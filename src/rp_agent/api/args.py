"""API 子命令参数解析器(轻量,零依赖)。"""
from __future__ import annotations

_SHORT_OPTS = {
    "-v": "--verbose",
    "-f": "--force",
    "-m": "--modify",
    "-t": "--timeout",
}
_VALUE_OPTS = {"--name", "--url", "--key", "--model", "--timeout"}
_LIST_OPTS = {"--filter", "--set"}
_FLAG_OPTS = {"--verbose", "--force", "--modify", "--pull", "--set-default"}

# 全部已知选项(供 shell 着色判定)
KNOWN_OPTIONS: set[str] = _VALUE_OPTS | _LIST_OPTS | _FLAG_OPTS | {"--help", "-h"}


def parse_args(argv: list[str]) -> tuple[dict[str, object], list[str]]:
    """解析 --key value / --flag / 短选项 / 位置参数。

    - 取值选项:--name/--url/--key/--model/--timeout(缺值抛 ValueError)
    - 列表选项:--filter/--set 可多次,收集为 list
    - 无值选项:--verbose/--force/--modify/--pull/--set-default → ""
    - 短选项经 _SHORT_OPTS 映射;未知 --xxx 抛 ValueError
    """
    opts: dict[str, object] = {}
    positional: list[str] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        long = _SHORT_OPTS.get(tok, tok)
        if long.startswith("--"):
            if long in _LIST_OPTS:
                if i + 1 >= len(argv):
                    raise ValueError(f"选项 {tok} 缺少值")
                opts.setdefault(long[2:], []).append(argv[i + 1])
                i += 2
            elif long in _VALUE_OPTS:
                if i + 1 >= len(argv):
                    raise ValueError(f"选项 {tok} 缺少值")
                opts[long[2:]] = argv[i + 1]
                i += 2
            elif long in _FLAG_OPTS:
                opts[long[2:]] = ""
                i += 1
            else:
                raise ValueError(f"未知选项: {tok}")
            continue
        if tok.startswith("-") and len(tok) > 1:
            raise ValueError(f"未知选项: {tok}")
        positional.append(tok)
        i += 1
    return opts, positional
