# Canonical transparent Graf-Id logo assets for Tauri and web favicons.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path $PSScriptRoot -Parent
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ExportScript = Join-Path $PSScriptRoot "export_graf_id_logo.py"

if (Test-Path $VenvPython) {
    & $VenvPython $ExportScript
} else {
    python $ExportScript
    if ($LASTEXITCODE -ne 0) {
        throw "export_graf_id_logo.py failed. Install Pillow in .venv or system Python."
    }
}

Write-Host "Canonical logo + transparent favicons written to desktop/public/ and desktop/src/assets/"
Write-Host "Verify: .venv\\Scripts\\python.exe packaging\\verify_favicons.py"
