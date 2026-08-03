from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_start_scripts_exist_and_nonempty():
    for name in ("start.bat", "start.ps1", "start.sh", "start_ps.bat"):
        script = ROOT / name
        assert script.exists(), f"缺少启动脚本 {name}"
        assert script.read_text(encoding="utf-8", errors="ignore").strip()
