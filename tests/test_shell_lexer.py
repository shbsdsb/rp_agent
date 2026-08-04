from rp_agent.shell import SHELL_STYLE, ShellLexer


def _tokens(text: str):
    lexer = ShellLexer()
    doc = type("Doc", (), {"text": text})()
    get_line = lexer.lex_document(doc)
    return [(style, frag) for style, frag in get_line(0) if frag]


def test_style_colors_are_valid():
    """prompt_toolkit 颜色名必须有效(如 opt 用 ansibrightblack 而非不存在的 ansigray)。"""
    for style_class in ("cmd", "param", "opt"):
        attrs = SHELL_STYLE.get_attrs_for_style_str(f"class:{style_class}")
        assert attrs.color, f"class:{style_class} 缺少有效颜色"


def test_known_command_is_cmd():
    assert _tokens("config") == [("class:cmd", "config")]


def test_command_and_valid_param():
    assert _tokens("api list") == [
        ("class:cmd", "api"),
        ("class:space", " "),
        ("class:param", "list"),
    ]


def test_new_subcommands_are_valid_params():
    for sub in ("pull", "sync", "modify"):
        tokens = _tokens(f"api {sub}")
        assert tokens[2] == ("class:param", sub), f"{sub} 应为有效参数"


def test_invalid_param_stays_default():
    # "demo" 不是 api 的合法参数 → 默认白色
    assert _tokens("api demo") == [
        ("class:cmd", "api"),
        ("class:space", " "),
        ("class:default", "demo"),
    ]


def test_long_option_is_gray():
    assert _tokens("config --help")[2] == ("class:opt", "--help")


def test_short_option_is_gray():
    assert _tokens("config -h")[2] == ("class:opt", "-h")


def test_new_long_option_is_gray():
    # --name 等新增 api 选项也应为灰色(tokens: api/add/--name/d)
    assert _tokens("api add --name d")[4] == ("class:opt", "--name")


def test_short_option_m_is_gray():
    # -m(等效 --modify)也应为灰色:api deepseek -m
    assert _tokens("api deepseek -m")[4] == ("class:opt", "-m")


def test_invalid_option_stays_default():
    assert _tokens("config --wat")[2] == ("class:default", "--wat")


def test_unknown_first_word_is_default():
    assert _tokens("foobar x")[0] == ("class:default", "foobar")


def test_trailing_space_preserved():
    assert _tokens("config ")[1] == ("class:space", " ")


def test_mode_commands_are_cmd():
    for name in ("chat", "rp", "agent"):
        assert _tokens(name) == [("class:cmd", name)]


def test_escaped_command_keeps_coloring():
    # 模式内 / 转义命令:剥掉 / 后仍按已知命令着色
    assert _tokens("/api list") == [
        ("class:cmd", "/api"),
        ("class:space", " "),
        ("class:param", "list"),
    ]


def test_escaped_exit_is_cmd():
    # /exit 是模式内主要退出命令,应着色为有效命令
    assert _tokens("/exit") == [("class:cmd", "/exit")]


def test_escaped_unknown_stays_default():
    assert _tokens("/foobar")[0] == ("class:default", "/foobar")


def test_api_use_set_are_valid_params():
    for sub in ("use", "set"):
        tokens = _tokens(f"api {sub}")
        assert tokens[2] == ("class:param", sub)


def test_chat_session_commands_are_cmd():
    for name in ("new", "list", "load"):
        assert _tokens(f"/{name}") == [("class:cmd", f"/{name}")]


def test_chat_subcommands_are_valid_params():
    for sub in ("list", "get", "load", "rename"):
        tokens = _tokens(f"chat {sub}")
        assert tokens[2] == ("class:param", sub)
