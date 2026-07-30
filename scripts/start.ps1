Set-Location -Path (Split-Path -Parent $PSScriptRoot)

$python = $null
if (Test-Path ".venv\Scripts\python.exe") {
    $python = ".\.venv\Scripts\python.exe"
} elseif (Test-Path "venv\Scripts\python.exe") {
    $python = ".\venv\Scripts\python.exe"
} else {
    $python = "python"
}

& $python scripts\kill_port_8000.py
& $python main.py
