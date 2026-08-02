#!/usr/bin/env bash
# rp-agent launcher script (Unix-like)
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "[rp-agent] uv not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

uv sync >/dev/null
if [ "$#" -eq 0 ]; then
    exec uv run rp-agent shell
fi
exec uv run rp-agent "$@"
