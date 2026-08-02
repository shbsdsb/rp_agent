from pathlib import Path

import pytest

from rp_agent import storage


def test_data_dir_points_to_project_root():
    expected = Path(__file__).resolve().parents[1] / "data"
    assert storage.DATA_DIR == expected


def test_ensure_dirs_creates_subdirs(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    storage.ensure_dirs()
    for name in ("characters", "chats", "presets", "api"):
        assert (tmp_path / name).is_dir()
    storage.ensure_dirs()  # 幂等,不抛错


def test_json_write_read_roundtrip(tmp_path):
    p = tmp_path / "nested" / "data.json"
    storage.json_write(p, {"a": 1, "b": [1, 2]})
    assert storage.json_read(p) == {"a": 1, "b": [1, 2]}


def test_json_read_missing_returns_none(tmp_path):
    assert storage.json_read(tmp_path / "nope.json") is None


def test_json_read_broken_returns_none(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text("{not json", encoding="utf-8")
    assert storage.json_read(p) is None


def test_safe_path_normal(monkeypatch, tmp_path):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    result = storage.safe_path("characters/alice.json")
    assert result == (tmp_path / "characters" / "alice.json").resolve()


@pytest.mark.parametrize("bad", ["../evil.json", "a/../../evil.json"])
def test_safe_path_rejects_traversal(monkeypatch, tmp_path, bad):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)
    with pytest.raises(ValueError):
        storage.safe_path(bad)
