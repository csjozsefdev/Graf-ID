# Canonical transparent Graf-Id logo assets for Tauri and web favicons.
$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path $PSScriptRoot -Parent
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ExportScript = Join-Path $PSScriptRoot "export_graf_id_logo.py"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

# The generated icons and logo assets are committed. Regenerating them needs
# Pillow; without it (a clean CI runner, a fresh venv) keep the committed files
# instead of failing, or silently continuing after a Python traceback.
& $Python -c "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('PIL') else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Pillow is not installed for $Python; keeping the committed icons and logo assets."
    return
}

& $Python $ExportScript
if ($LASTEXITCODE -ne 0) {
    throw "export_graf_id_logo.py failed (exit code $LASTEXITCODE)."
}

Write-Host "Canonical logo + transparent favicons written to desktop/public/ and desktop/src/assets/"
Write-Host "Verify: .venv\\Scripts\\python.exe packaging\\verify_favicons.py"
