# Remove Graf-Id packaged-runtime env vars from User scope and the current shell.
# Safe to run after release smoke tests left PYTHONHOME/GRAFID_* in your terminal.

$ErrorActionPreference = "Stop"

$names = @(
    "GRAFID_PYTHON",
    "GRAFID_RUNTIME_MODE",
    "GRAFID_RESOURCE_ROOT",
    "GRAFID_RESOURCE_DIR",
    "GRAFID_DATA_DIR",
    "PYTHONHOME",
    "PYTHONPATH",
    "PYTHONNOUSERSITE"
)

foreach ($name in $names) {
    [Environment]::SetEnvironmentVariable($name, $null, "User")
    Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
}

Write-Host "Cleared Graf-Id runtime env vars from User scope and this shell."
Write-Host "Restart Cursor/terminals if another app still inherits old values."
