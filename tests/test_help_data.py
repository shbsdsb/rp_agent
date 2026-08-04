from rp_agent.help_data import HELP_ENTRIES, find_entry


def test_entries_have_required_fields():
    for entry in HELP_ENTRIES:
        assert entry["command"]
        assert entry["desc"]
        assert entry["usage"]
        assert isinstance(entry["params"], list)


def test_command_names_unique():
    names = [e["command"] for e in HELP_ENTRIES]
    assert len(names) == len(set(names))


def test_aliases_unique_and_no_overlap():
    aliases = [a for e in HELP_ENTRIES for a in e["aliases"]]
    assert len(aliases) == len(set(aliases))  # 无重复别名
    names = {e["command"] for e in HELP_ENTRIES}
    assert not (set(aliases) & names)  # 别名不与命令名重叠


def test_find_entry_by_command_and_alias():
    assert find_entry("help") is not None
    assert find_entry("?") is not None
    assert find_entry("quit") is not None
    assert find_entry("nope") is None


def test_mode_entries_exist():
    for name in ("chat", "rp", "agent"):
        assert find_entry(name) is not None


def test_config_entry_explains_fields():
    entry = find_entry("config")
    assert entry is not None
    params_text = " ".join(p for p, _ in entry["params"])
    assert "log_level" in params_text
    assert "timeout" in params_text


def test_storage_entry_removed():
    assert find_entry("storage") is None


def test_api_entry_mentions_use_set():
    entry = find_entry("api")
    params_text = " ".join(p for p, _ in entry["params"])
    assert "use <name>" in params_text
    assert "set <name>" in params_text


def test_chat_entry_explains_subcommands():
    entry = find_entry("chat")
    params_text = " ".join(p for p, _ in entry["params"])
    for sub in ("list", "get", "load", "rename"):
        assert sub in params_text
