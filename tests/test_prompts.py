from pathlib import Path

SYSTEM_DIR = (
    Path(__file__).resolve().parents[1]
    / "src" / "rp_agent" / "prompts" / "system"
)


def test_default_prompt_exists_and_nonempty():
    prompt_file = SYSTEM_DIR / "default.md"
    assert prompt_file.exists()
    assert prompt_file.read_text(encoding="utf-8").strip()
