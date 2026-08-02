from rp_agent.shell import ShellLexer


def _tokens(text: str):
    lexer = ShellLexer()
    doc = type("Doc", (), {"text": text})()
    get_line = lexer.lex_document(doc)
    return [(style, frag) for style, frag in get_line(0) if frag]


def test_known_command_is_cmd():
    assert _tokens("config") == [("class:cmd", "config")]


def test_command_and_valid_param():
    assert _tokens("api list") == [
        ("class:cmd", "api"),
        ("class:space", " "),
        ("class:param", "list"),
    ]


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


def test_invalid_option_stays_default():
    assert _tokens("config --wat")[2] == ("class:default", "--wat")


def test_unknown_first_word_is_default():
    assert _tokens("foobar x")[0] == ("class:default", "foobar")


def test_trailing_space_preserved():
    assert _tokens("config ")[1] == ("class:space", " ")
