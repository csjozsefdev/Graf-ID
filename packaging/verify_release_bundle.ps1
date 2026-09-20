# Smoke-test the Tauri release layout without repo .venv (IPC + optional UI launch).
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$ReleaseDir = Join-Path $RepoRoot "desktop\src-tauri\target\release"
$ReleaseExe = Join-Path $ReleaseDir "graf-id-desktop.exe"
$BundleRoot = Join-Path $ReleaseDir "bundle"

if (-not (Test-Path $ReleaseExe)) {
    throw "Release binary missing. Run packaging\build_release.ps1 or npm run tauri:build first: $ReleaseExe"
}

$Python = Join-Path $ReleaseDir "runtime\python.exe"
if (-not (Test-Path $Python)) {
    throw "Bundled python missing: $Python"
}

$RuntimeDir = $Python | Split-Path -Parent
$SitePackages = Join-Path $RuntimeDir "Lib\site-packages"
if (-not (Test-Path $SitePackages)) {
    throw "Missing site-packages: $SitePackages"
}

$DataDir = Join-Path $env:TEMP "grafid-release-smoke-$(Get-Random)"
New-Item -ItemType Directory -Force -Path $DataDir | Out-Null

$managedEnvVars = @(
    "GRAFID_RUNTIME_MODE",
    "GRAFID_DATA_DIR",
    "GRAFID_PYTHON",
    "GRAFID_RESOURCE_ROOT",
    "PYTHONPATH",
    "PYTHONHOME",
    "PYTHONNOUSERSITE",
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
    $env:PYTHONHOME = $RuntimeDir
    $env:PYTHONNOUSERSITE = "1"
    $env:PATH = ($env:PATH -split ';' | Where-Object { $_ -notmatch '\\\.venv\\' }) -join ';'

    Write-Host "Release binary: $ReleaseExe"
Write-Host "Bundled Python: $Python"
Write-Host "Data dir:       $DataDir"

if (Test-Path $BundleRoot) {
    $installers = Get-ChildItem -Path $BundleRoot -Recurse -Include "*.msi", "*setup.exe" -ErrorAction SilentlyContinue
    foreach ($item in $installers) {
        Write-Host "Installer:      $($item.FullName) ($([math]::Round($item.Length / 1MB, 2)) MB)"
    }
} else {
    Write-Host "Bundle folder:  (not found - binary-only smoke)"
}

function Invoke-Ipc($cmd, [string[]]$Extra = @()) {
    $ipcArgs = @("-m", "grafid.cli.main", "ipc", $cmd) + $Extra
    $out = & $Python @ipcArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw "ipc $cmd failed: $out" }
    return ($out | Where-Object { $_ -match '^\{' } | Select-Object -Last 1)
}

$health = Invoke-Ipc "health" | ConvertFrom-Json
if (-not $health.ok) { throw "health failed" }
if ($health.data.runtime_mode -ne "packaged") {
    throw "expected packaged mode, got $($health.data.runtime_mode)"
}
Write-Host "health: ok"

$check = Invoke-Ipc "runtime-check" | ConvertFrom-Json
if (-not $check.ok) { throw "runtime-check failed" }
Write-Host "runtime-check: ok"

$boot = Invoke-Ipc "bootstrap" | ConvertFrom-Json
if (-not $boot.ok) { throw "bootstrap failed" }
Write-Host "bootstrap: ok (projects=$($boot.data.projects.Count))"

$card = $boot.data.startup_card
if ($null -ne $card) {
    Write-Host "startup_card: visible=$($card.visible) id=$($card.startup_summary_id)"
}

if ($card -and $card.visible -and $card.startup_summary_id) {
    $sid = $card.startup_summary_id.ToString()
    $dismiss = Invoke-Ipc "dismiss-startup" @("0", "--summary-id", $sid) | ConvertFrom-Json
    if (-not $dismiss.ok) { throw "dismiss-startup failed" }
    Write-Host "dismiss-startup: ok"
}

$configPath = Join-Path $DataDir "config.json"
$dbPath = Join-Path $DataDir "graf-id.db"
if (-not (Test-Path $configPath)) { throw "config not created: $configPath" }
if (-not (Test-Path $dbPath)) { throw "database not created: $dbPath" }
Write-Host "config:   $configPath"
Write-Host "database: $dbPath"

# Seed one project for dashboard IPC (no .venv).
$sampleRoot = Join-Path $DataDir "sample-project"
New-Item -ItemType Directory -Force -Path $sampleRoot | Out-Null
Set-Content -Path (Join-Path $sampleRoot "main.py") -Value "# TODO: release smoke`n" -Encoding utf8
& $Python -m grafid.cli.main add "release-smoke" $sampleRoot 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) { throw "graf-id add failed" }
$dash = Invoke-Ipc "dashboard" | ConvertFrom-Json
if (-not $dash.ok) { throw "dashboard failed" }
if ($dash.data.projects.Count -lt 1) { throw "dashboard returned no projects" }
Write-Host "dashboard: ok (projects=$($dash.data.projects.Count))"

    # Launch the release .exe with isolated user data (no GRAFID_PYTHON override).
    $launchData = Join-Path $env:TEMP "grafid-release-ui-$(Get-Random)"
    New-Item -ItemType Directory -Force -Path $launchData | Out-Null
    $env:GRAFID_DATA_DIR = $launchData
    Remove-Item Env:GRAFID_PYTHON -ErrorAction SilentlyContinue
    Remove-Item Env:GRAFID_RESOURCE_ROOT -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
    Remove-Item Env:GRAFID_RUNTIME_MODE -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONNOUSERSITE -ErrorAction SilentlyContinue

    Write-Host "Launching UI binary (isolated data: $launchData) ..."
$proc = Start-Process -FilePath $ReleaseExe -WorkingDirectory $ReleaseDir -PassThru
$logPath = Join-Path $launchData "logs\desktop-backend.log"
$deadline = (Get-Date).AddSeconds(90)
$backendOk = $false
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 2
    if (Test-Path (Join-Path $launchData "graf-id.db")) {
        $backendOk = $true
        break
    }
    if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
        break
    }
}
if ($proc -and (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
if (-not $backendOk) {
    $logTail = ""
    if (Test-Path $logPath) {
        $logTail = (Get-Content $logPath -Tail 20) -join "`n"
    }
    throw "UI launch did not initialize database within 90s. Log tail:`n$logTail"
}
Write-Host "UI launch: ok (database created under isolated data dir)"
if (Test-Path $logPath) {
    Write-Host "backend log: $logPath"
}

    Write-Host "Release bundle smoke test PASSED"
}
finally {
    Restore-ShellEnvironment
}
