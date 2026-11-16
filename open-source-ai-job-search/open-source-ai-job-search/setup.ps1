$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}

& .\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[all,dev]"

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

jobsearch init-db
Write-Host "Setup complete."
Write-Host "Run the offline demo: jobsearch run --no-llm"
Write-Host "Run the dashboard: jobsearch dashboard"
