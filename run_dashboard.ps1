$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment missing. Follow the installation steps in README.md."
}

& ".\.venv\Scripts\python.exe" -m streamlit run app.py --server.headless true --server.port 8502
