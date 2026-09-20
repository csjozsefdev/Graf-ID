# Smoke-test packaged runtime layout without launching the Tauri UI.
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeDir = Join-Path $RepoRoot "desktop\src-tauri\runtime"
$Python = Join-Path $RuntimeDir "python.exe"
$SitePackages = Join-Path $RuntimeDir "Lib\site-packages"
$DataDir = Join-Path $env:TEMP "grafid-packaged-smoke-$(Get-Random)"

if (-not (Test-Path $Python)) {
    throw "Missing $Python - run packaging\build_runtime.ps1 first"
}

New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

$managedEnvVars = @(
    "GRAFID_RUNTIME_MODE",
    "GRAFID_DATA_DIR",
    "GRAFID_PYTHON",
    "GRAFID_RESOURCE_ROOT",
    "PYTHONPATH",
    "PYTHONDONTWRITEBYTECODE"
)
$savedEnv = @{}
foreach ($name in $managedEnvVars) {
    $savedEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
}

function Restore-ShellEnvironment {
    foreach ($name in $managedEnvVars) {
        $previous = $savedEnv[$name]
        if ([string]::IsNullOrWhiteSpace($previous)) {
            Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path "Env:$name" -Value $previous
        }
    }
}

try {
    # Never add bytecode of our own to the runtime under test.
    $env:PYTHONDONTWRITEBYTECODE = "1"
    $env:GRAFID_RUNTIME_MODE = "packaged"
    $env:GRAFID_DATA_DIR = $DataDir
    $env:GRAFID_PYTHON = $Python
    $env:GRAFID_RESOURCE_ROOT = $SitePackages
    $env:PYTHONPATH = $SitePackages

    Write-Host "Data dir: $DataDir"
Write-Host "Runtime:  $Python"

function Invoke-Ipc($cmd) {
    $out = & $Python -m grafid.cli.main ipc $cmd 2>&1
    if ($LASTEXITCODE -ne 0) { throw "ipc $cmd failed: $out" }
    return ($out | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
}

$health = Invoke-Ipc "health" | ConvertFrom-Json
if (-not $health.ok) { throw "health not ok" }
Write-Host "health: ok (mode=$($health.data.runtime_mode))"

$check = Invoke-Ipc "runtime-check" | ConvertFrom-Json
if (-not $check.ok) { throw "runtime-check not ok" }
Write-Host "runtime-check: ok"

$boot = Invoke-Ipc "bootstrap" | ConvertFrom-Json
if (-not $boot.ok) { throw "bootstrap not ok" }
Write-Host "bootstrap: ok (projects=$($boot.data.projects.Count), schema=$($boot.data.schema_version))"

if ($boot.data.schema_version -ne 12) {
    throw "Expected schema_version 12 in bundled runtime, got $($boot.data.schema_version)"
}

$constantsPath = Join-Path $SitePackages "grafid\core\constants.py"
$constantsText = Get-Content $constantsPath -Raw
if ($constantsText -notmatch 'SCHEMA_VERSION = 12') {
    throw "Bundled grafid constants.py does not declare SCHEMA_VERSION = 12"
}

foreach ($cmd in @("add-project", "remove-project", "update-project", "refresh-resume", "close-session", "start-session", "session-timeline", "end-session")) {
    $help = & $Python -m grafid.cli.main ipc $cmd --help 2>&1
    if ($LASTEXITCODE -ne 0) { throw "Missing ipc command: $cmd" }
}
Write-Host "ipc commands: add/remove/update/refresh/close-session ok"

    Write-Host "Packaged runtime smoke test PASSED"
}
finally {
    Restore-ShellEnvironment
}
