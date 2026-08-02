# rp-agent launcher script (PowerShell)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "[rp-agent] uv not found. Install with: winget install --id=astral-sh.uv -e" -ForegroundColor Red
    exit 1
}

uv sync | Out-Null
if ($args.Count -eq 0) {
    uv run rp-agent shell
} else {
    uv run rp-agent @args
}
exit $LASTEXITCODE
