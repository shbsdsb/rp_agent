import pytest

from rp_agent.api.args import parse_args


def test_named_options():
    opts, pos = parse_args(
        ["--name", "demo", "--url", "https://x/v1", "--key", "k", "--model", "m"]
    )
    assert opts == {"name": "demo", "url": "https://x/v1", "key": "k", "model": "m"}
    assert pos == []


def test_flag_and_positional():
    opts, pos = parse_args(["demo", "--verbose"])
    assert opts == {"verbose": ""}
    assert pos == ["demo"]


def test_short_options():
    opts, _ = parse_args(["-v"])
    assert opts == {"verbose": ""}
    opts, _ = parse_args(["-f"])
    assert opts == {"force": ""}
    opts, _ = parse_args(["-t", "5"])
    assert opts == {"timeout": "5"}


def test_filter_and_set_multiple():
    opts, _ = parse_args(
        ["--filter", "model=gpt-4", "--filter", "base_url=x", "--set", "model=gpt-5"]
    )
    assert opts["filter"] == ["model=gpt-4", "base_url=x"]
    assert opts["set"] == ["model=gpt-5"]


def test_unknown_option_raises():
    with pytest.raises(ValueError, match="未知选项"):
        parse_args(["--wat"])


def test_missing_value_raises():
    with pytest.raises(ValueError, match="缺少值"):
        parse_args(["--name"])
