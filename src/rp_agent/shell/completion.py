"""词法着色与 Tab 补全:ShellLexer/SHELL_STYLE/ShellCompleter。

与 commands.py 共享 _KNOWN_COMMANDS/_COMMAND_ARGS/_VALID_OPTIONS 数据源,
保证"着色的词 = 可补全的词"。
"""
from __future__ import annotations

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.styles import Style

from rp_agent.api.store import list_connections
from rp_agent.shell.chat_cmds import _chat_business
from rp_agent.shell.commands import _COMMAND_ARGS, _KNOWN_COMMANDS, _VALID_OPTIONS

SHELL_STYLE = Style.from_dict(
    {
        "cmd": "ansiyellow bold",  # 有效命令:黄色
        "param": "ansibrightcyan",  # 有效参数:亮天蓝
        "opt": "ansibrightblack",  # 有效选项:灰色(prompt_toolkit 无 ansigray,用亮黑)
        "chat-prompt": "#FFE066 bold",  # chat 模式输入前缀:暖黄(与 assistant> 的 #66AAFF 区分)
        "status": "bg:#1a1a2e #e0e0e0",  # 状态栏:深底浅字
        "status-mode": "ansiyellow bold",
        "status-dim": "ansibrightblack",
        "hint": "ansibrightblack",
        # 其他 token(class:default)不定义:保持终端默认白色
    }
)


class ShellLexer(Lexer):
    """实时词法着色:有效命令黄、有效参数亮天蓝、有效选项灰,其余默认白。"""

    def lex_document(self, document):
        def get_line(lineno: int):
            if lineno != 0:
                return []
            tokens: list[tuple[str, str]] = []
            parts = document.text.split()
            index = 0
            first = parts[0] if parts else ""
            bare = first[1:] if first.startswith("/") else first  # / 转义命令剥前缀后判断
            is_known_cmd = bare in _KNOWN_COMMANDS
            valid_args = _COMMAND_ARGS.get(bare, set()) if is_known_cmd else set()
            for i, part in enumerate(parts):
                start = document.text.find(part, index)
                if start > index:
                    tokens.append(("class:space", document.text[index:start]))
                if i == 0 and is_known_cmd:
                    style = "class:cmd"
                elif part.startswith("-") and part in _VALID_OPTIONS:
                    style = "class:opt"
                elif i > 0 and part in valid_args:
                    style = "class:param"
                else:
                    style = "class:default"
                tokens.append((style, part))
                index = start + len(part)
            if index < len(document.text):
                tokens.append(("class:space", document.text[index:]))
            return tokens

        return get_line


# 命令名补全候选:已知命令 + / 转义变体(模式内 /load、/exit 等)
_COMMAND_NAMES: set[str] = _KNOWN_COMMANDS | {f"/{c}" for c in _KNOWN_COMMANDS}


class ShellCompleter(Completer):
    """全范围 Tab 补全(dropdown):命令名/蓝色子命令/灰色选项/连接名/会话名。

    与 ShellLexer 共用 _KNOWN_COMMANDS/_COMMAND_ARGS/_VALID_OPTIONS 数据源,
    保证"着色的词 = 可补全的词"。按正在输入词的 0-based 位置分派:
    0=命令名,1=蓝色子命令,2=第一位置参数(词以 - 开头时优先补选项)。
    """

    # (命令, 子命令) → 第一个位置参数类型;未列出者不补位置参数
    _POSITIONAL: dict[tuple[str, str], str] = {
        ("api", "get"): "connection",
        ("api", "del"): "connection",
        ("api", "test"): "connection",
        ("api", "pull"): "connection",
        ("api", "sync"): "connection",
        ("api", "modify"): "connection",
        ("api", "use"): "connection",
        ("api", "set"): "connection",
        ("chat", "get"): "session",
        ("chat", "load"): "session",
        ("chat", "rename"): "session",
    }

    def get_completions(self, document, complete_event):
        text = document.text
        if not text.strip():
            yield from self._words(_COMMAND_NAMES, document, complete_event)
            return
        parts = text.split()
        # 尾空格说明上一词已完成、正在输入新词
        position = len(parts) if text.endswith(" ") else len(parts) - 1
        if position == 0:
            yield from self._words(_COMMAND_NAMES, document, complete_event)
            return
        first = parts[0]
        if first == "/load" and position == 1:
            yield from self._sessions(document, complete_event)
            return
        cmd = first.lstrip("/")
        if position == 1:
            subs = _COMMAND_ARGS.get(cmd, set())
            if subs:
                yield from self._words(subs, document, complete_event)
            return
        current = parts[-1]
        if current.startswith("-"):
            # 选项补全:任意后续位置(第 3+ 词)均可补,与规格一致
            if position >= 2:
                yield from self._words(_VALID_OPTIONS, document, complete_event)
            return
        if position != 2:
            return  # 只补第一个位置参数(chat rename 第二参等不补)
        ptype = self._POSITIONAL.get((cmd, parts[1]))
        if ptype == "connection":
            try:
                names = list_connections()
            except Exception:
                return
            yield from self._words(names, document, complete_event)
        elif ptype == "session":
            yield from self._sessions(document, complete_event)

    def _sessions(self, document, complete_event):
        try:
            names = _chat_business("session_names")() or []
        except Exception:
            return
        yield from self._words(names, document, complete_event)

    @staticmethod
    def _words(words, document, complete_event):
        """对 words 做大小写不敏感前缀补全。

        用 WORD=True 提取正在输入的完整词(含 / 前缀、-- 选项等,
        仅以空白分界),避免 WordCompleter 的字母数字正则把 / 当分隔符。
        """
        if not words:
            return
        word = document.get_word_before_cursor(WORD=True)
        lower = word.lower()
        for w in sorted(words):
            if w.lower().startswith(lower):
                yield Completion(text=w, start_position=-len(word) if word else 0)


_pt_history = InMemoryHistory()
