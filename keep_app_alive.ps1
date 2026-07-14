$ErrorActionPreference = "SilentlyContinue"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Ports = @(8501, 8502)
$Python = Join-Path $Root ".venv\Scripts\python.exe"

function Test-AppHealth {
    param([int]$Port)
    $HealthUrl = "http://localhost:$Port/_stcore/health"
    try {
        $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
        return $response.StatusCode -eq 200 -and $response.Content -match "ok"
    } catch {
        return $false
    }
}

function Stop-PortOwner {
    param([int]$Port)
    $connections = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    foreach ($connection in $connections) {
        if ($connection.OwningProcess) {
            Stop-Process -Id $connection.OwningProcess -Force -ErrorAction SilentlyContinue
        }
    }
}

function Start-OptionsApp {
    param([int]$Port)
    if (-not (Test-Path $Python)) {
        return
    }
    Start-Process `
        -FilePath $Python `
        -ArgumentList @("-m", "streamlit", "run", "app.py", "--server.headless", "true", "--server.port", "$Port") `
        -WorkingDirectory $Root `
        -WindowStyle Hidden
}

Set-Location $Root

foreach ($Port in $Ports) {
    if (-not (Test-AppHealth -Port $Port)) {
        Stop-PortOwner -Port $Port
        Start-OptionsApp -Port $Port
    }
}

while ($true) {
    Start-Sleep -Seconds 12
    foreach ($Port in $Ports) {
        if (-not (Test-AppHealth -Port $Port)) {
            Stop-PortOwner -Port $Port
            Start-Sleep -Seconds 2
            Start-OptionsApp -Port $Port
        }
    }
}
