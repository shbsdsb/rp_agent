from pathlib import Path

SYSTEM_DIR = (
    Path(__file__).resolve().parents[1]
    / "src" / "rp_agent" / "prompts" / "system"
)


def test_default_prompt_exists_and_nonempty():
    prompt_file = SYSTEM_DIR / "default.md"
    assert prompt_file.exists()


def test_mode_prompts_exist():
    for name in ("chat", "rp", "agent"):
        prompt_file = SYSTEM_DIR / f"{name}.txt"
        assert prompt_file.exists(), f"缺少 prompts/system/{name}.txt"
