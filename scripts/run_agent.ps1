param(
    [string]$Python = ".venv-experiments/Scripts/python.exe",
    [string]$CarlaExe = "",
    [int]$Port = 2000,
    [switch]$NoWatch
)
# Optionally start a visible CARLA server, run the preflight, then run one sensor study per typed prompt.
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$root = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $root
try {
    if (-not (Test-Path -LiteralPath $Python)) { throw "Backend Python not found: $Python (pass -Python <path-to-python.exe>)" }
    $listening = { [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) }
    if (-not (& $listening)) {
        if (-not $CarlaExe) { throw "No CARLA server on port $Port. Start it first or pass -CarlaExe <path-to-CarlaUE4.exe>" }
        Write-Host "Starting CARLA (visible, Low quality)..."
        Start-Process -FilePath $CarlaExe -WorkingDirectory (Split-Path -Parent $CarlaExe) -ArgumentList `
            "/Game/Carla/Maps/Town01", "-quality-level=Low", "-windowed", "-ResX=960", "-ResY=540", "-dx11", "-nosound", "-carla-rpc-port=$Port"
        $deadline = (Get-Date).AddMinutes(3)
        while (-not (& $listening)) {
            if ((Get-Date) -gt $deadline) { throw "CARLA did not open port $Port within 3 minutes" }
            Start-Sleep -Seconds 3
        }
        Start-Sleep -Seconds 15
    }
    & $Python -m scripts.check_carla
    if ($LASTEXITCODE -ne 0) { throw "CARLA preflight failed; fix it before running studies" }
    $watch = if ($NoWatch) { @() } else { @("--watch") }
    while ($true) {
        Write-Host ""
        $message = Read-Host "Prompt (empty line to quit)"
        if ([string]::IsNullOrWhiteSpace($message)) { break }
        & $Python -m scripts.test_sensor_agent @watch --message $message
        if ($LASTEXITCODE -eq 0) { Write-Host "Study finished; results are in the Artifacts folder printed above." -ForegroundColor Green }
        else { Write-Host "Study failed (exit $LASTEXITCODE); read the log above." -ForegroundColor Red }
    }
} finally { Pop-Location }
