param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (-not (Test-Path ".venv-lab/Scripts/python.exe")) {
        & $Python -m venv .venv-lab
        if ($LASTEXITCODE -ne 0) { throw "Install Python 3.12 and pass -Python <path-to-python.exe>" }
    }
    & .venv-lab/Scripts/python.exe -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }
    & .venv-lab/Scripts/python.exe scripts/check_lab_data.py
    if ($LASTEXITCODE -ne 0) { throw "Lab data check failed" }
    Write-Host "Start API: .venv-lab/Scripts/python.exe -m uvicorn src.main:app --reload"
} finally { Pop-Location }
