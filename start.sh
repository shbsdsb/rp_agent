#!/usr/bin/env bash
# rp-agent 通用启动脚本(类 Unix)
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo "[rp-agent] 未找到 uv,请先安装: curl -LsSf https://astral.sh/uv/install.sh | sh" >&2
    exit 1
fi

uv sync >/dev/null
exec uv run rp-agent "$@"
