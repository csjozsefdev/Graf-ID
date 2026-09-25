# Build embedded Python runtime for Graf-Id desktop (Windows).
# Output: desktop/src-tauri/runtime/ (bundled by Tauri as resources)
# The runtime is built from scratch on every run: stale release output is
# cleared, only what the app needs is copied (no stdlib tests, IDLE, Tk, pip
# bootstrap, grafid tests or developer caches), bytecode is compiled here with
# the pinned interpreter, and a final audit fails the build on any violation.
# Requires: a .venv built from Python $RequiredPythonVersion (see below) with
# graf-id installed (pip install -e ".[dev]")

param(
    [switch]$UpgradePip
)

$ErrorActionPreference = "Stop"

# Pinned release-runtime interpreter. This is what gets embedded and shipped
# to end users, so it must not silently follow "whatever system Python this
# developer's machine happens to have" (that previously shipped 3.14.5 on
# one machine while Docker/CI test against 3.12 — a real, undetected
# version drift found during 1.0.0 release verification). 3.12.10 was
# chosen because it's the exact version reproducibly installable via
# `winget install --id Python.Python.3.12 --version 3.12.10` today, and it
# matches the 3.12 minor line the Dockerfile (python:3.12-slim) and CI
# (actions/setup-python@v5, python-version: "3.12") already test against.
# Bump this deliberately (and re-verify) if a newer 3.12.x patch is needed;
# never let it silently drift.
$RequiredPythonVersion = "3.12.10"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$RuntimeRequirements = Join-Path $PSScriptRoot "runtime-requirements.txt"
$OutputDir = Join-Path $RepoRoot "desktop\src-tauri\runtime"
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    throw "Missing .venv. From repo root run: python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`""
}

function Initialize-VenvBuildEnvironment {
    # Packaged-runtime env vars (often set during release QA) break repo .venv imports.
    foreach ($name in @(
            "PYTHONHOME",
            "PYTHONPATH",
            "PYTHONNOUSERSITE",
            "GRAFID_PYTHON",
            "GRAFID_RUNTIME_MODE",
            "GRAFID_RESOURCE_ROOT"
        )) {
        Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
    }
}

Initialize-VenvBuildEnvironment

function Normalize-WindowsPath {
    param([string]$Path)
    if ([string]::IsNullOrWhiteSpace($Path)) {
        return $null
    }
    $normalized = $Path.Trim()
    if ($normalized.StartsWith("\\?\")) {
        $normalized = $normalized.Substring(4)
    }
    return $normalized
}

function Assert-RuntimePath {
    param(
        [string]$Path,
        [string]$Label
    )
    $normalized = Normalize-WindowsPath $Path
    if ([string]::IsNullOrWhiteSpace($normalized)) {
        throw "$Label is missing. Expected a Python install directory from packaging\_python_base_info.py."
    }
    if (-not (Test-Path $normalized)) {
        throw "$Label was not found: $normalized"
    }
    return $normalized
}

Write-Host "Building Graf-Id embedded runtime -> $OutputDir"

$pyInfoScript = Join-Path $PSScriptRoot "_python_base_info.py"
if (-not (Test-Path $pyInfoScript)) {
    throw "Missing helper script: $pyInfoScript"
}

$pyMeta = & $VenvPython $pyInfoScript 2>&1
if ($LASTEXITCODE -ne 0) {
    $detail = ($pyMeta | Out-String).Trim()
    if ($detail -match "PYTHONHOME|encodings|embedded Python") {
        throw @(
            "Failed to resolve base Python install via $pyInfoScript."
            "Your shell may still have packaged-runtime env vars (PYTHONHOME, PYTHONPATH, GRAFID_PYTHON)."
            "Remove them, then retry: Remove-Item Env:PYTHONHOME, Env:PYTHONPATH, Env:GRAFID_PYTHON -ErrorAction SilentlyContinue"
            $detail
        ) -join " "
    }
    throw "Failed to resolve base Python install via $pyInfoScript. $detail"
}
$pyMeta = ($pyMeta | Where-Object { $_ -is [string] } | Select-Object -Last 1)
if ($pyMeta -is [System.Management.Automation.ErrorRecord]) {
    $pyMeta = $pyMeta.ToString()
}
if ([string]::IsNullOrWhiteSpace($pyMeta)) {
    throw "No output from $pyInfoScript. Expected JSON with base Python path."
}

$meta = $pyMeta | ConvertFrom-Json
$Base = Assert-RuntimePath -Path $meta.base -Label "Base Python install"
$Ver = [string]$meta.ver
if ([string]::IsNullOrWhiteSpace($Ver)) {
    throw "Python version tag is missing from $pyInfoScript output."
}
$FullVer = [string]$meta.full_ver
if ([string]::IsNullOrWhiteSpace($FullVer)) {
    throw "Full Python version is missing from $pyInfoScript output."
}
if ($FullVer -ne $RequiredPythonVersion) {
    throw @(
        "Refusing to build the release runtime with Python $FullVer."
        "The embedded runtime must be built with exactly Python $RequiredPythonVersion"
        "(pinned in this script) so the shipped interpreter matches the version"
        "Docker/CI test against, instead of silently following whatever system"
        "Python happens to be installed on this machine."
        "Install it (winget install --id Python.Python.3.12 --version $RequiredPythonVersion),"
        "recreate .venv from that install (python -m venv .venv; .venv\Scripts\pip install -e `".[dev]`"),"
        "and retry."
    ) -join " "
}

$BasePythonExe = Join-Path $Base "python.exe"
if (-not (Test-Path $BasePythonExe)) {
    throw "Base Python executable was not found: $BasePythonExe"
}

Write-Host "Using base Python install: $Base"

$baseLower = $Base.ToLowerInvariant()
$blockedPathMarkers = @(
    "\codex\",
    "\src-tauri\runtime\",
    "\.cursor\",
    "\embeddable"
)
foreach ($marker in $blockedPathMarkers) {
    if ($baseLower.Contains($marker)) {
        throw @(
            "Refusing to package from embedded or dev-only Python path: $Base"
            "Recreate the repo .venv from a normal system Python install, then retry."
        ) -join " "
    }
}

# Every release entry point runs this script first: build_release.ps1 calls it
# directly, and `npm run tauri:build` / `tauri build` run it as tauri.conf.json's
# beforeBuildCommand (npm run build:runtime). Tauri copies bundle.resources
# (runtime/ -> target/release/runtime/) over whatever is already there and never
# deletes files that disappeared from the source, so a target/release/runtime/
# or bundle/ left over from an earlier build (other Python version, files this
# script no longer ships, old installers) would silently be reused. Clearing
# them HERE - not only in build_release.ps1 - is what makes every entry point
# start from a clean slate.
$ReleaseTarget = Join-Path $RepoRoot "desktop\src-tauri\target\release"
foreach ($name in @("runtime", "bundle")) {
    $stale = Join-Path $ReleaseTarget $name
    if (Test-Path $stale) {
        Write-Host "Removing stale release output: $stale"
        Remove-Item -Recurse -Force $stale
    }
}

if (Test-Path $OutputDir) {
    Remove-Item -Recurse -Force $OutputDir
}
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

function Copy-IfExists($src, $destDir) {
    if (Test-Path $src) {
        Copy-Item -Path $src -Destination $destDir -Force
        return $true
    }
    return $false
}

# robocopy so the exclusions apply at copy time (nothing unwanted is ever
# copied and then deleted). Exit codes 0-7 are success; >= 8 is a failure.
function Copy-Tree {
    param(
        [string]$Source,
        [string]$Destination,
        [string[]]$ExcludeDirs = @(),
        [string[]]$ExcludeFiles = @()
    )
    $roboArgs = @($Source, $Destination, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/R:1", "/W:1")
    if ($ExcludeDirs.Count -gt 0) { $roboArgs += "/XD"; $roboArgs += $ExcludeDirs }
    if ($ExcludeFiles.Count -gt 0) { $roboArgs += "/XF"; $roboArgs += $ExcludeFiles }
    & robocopy @roboArgs | Out-Null
    if ($LASTEXITCODE -ge 8) {
        throw "robocopy failed with exit code $LASTEXITCODE copying $Source"
    }
    $global:LASTEXITCODE = 0
}

# Core interpreter files from the base Python install
$binaryNames = @(
    "python.exe",
    "python$Ver.dll",
    "python3.dll",
    "vcruntime140.dll",
    "vcruntime140_1.dll"
)
foreach ($name in $binaryNames) {
    if (-not (Copy-IfExists (Join-Path $Base $name) $OutputDir)) {
        Copy-IfExists (Join-Path $Base "Scripts\$name") $OutputDir | Out-Null
    }
}

# CPython's license (PSF) must travel with the interpreter it covers.
$pythonLicense = Join-Path $Base "LICENSE.txt"
if (-not (Test-Path $pythonLicense)) {
    throw "CPython LICENSE.txt not found in the base Python install: $pythonLicense"
}
Copy-Item -Force $pythonLicense (Join-Path $OutputDir "LICENSE-PYTHON.txt")

# Extension modules. Test-only modules and the Tk runtime (Tkinter is never used
# by Graf-Id, and this layout has no tcl/ data directory for it anyway) stay out.
$dlls = Join-Path $Base "DLLs"
if (Test-Path $dlls) {
    Copy-Tree -Source $dlls -Destination (Join-Path $OutputDir "DLLs") `
        -ExcludeFiles @("_test*.pyd", "_ctypes_test.pyd", "_tkinter.pyd", "tcl86t.dll", "tk86t.dll")
}

# Standard library (required for encodings and stdlib imports), minus what a
# shipped application never needs: CPython's own test suite, IDLE, Tkinter and
# turtle, pip's bootstrap (ensurepip), lib2to3, venv, pydoc topic data and
# msilib. site-packages is created fresh below, and NO bytecode is copied from
# the developer's Python: bytecode is generated from scratch further down with
# the pinned interpreter itself.
$baseLib = Join-Path $Base "Lib"
$outLib = Join-Path $OutputDir "Lib"
$stdlibExcludedDirs = @(
    "test", "idlelib", "tkinter", "turtledemo", "ensurepip",
    "lib2to3", "venv", "pydoc_data", "msilib", "site-packages"
) | ForEach-Object { Join-Path $baseLib $_ }
if (Test-Path $baseLib) {
    Copy-Tree -Source $baseLib -Destination $outLib `
        -ExcludeDirs (@($stdlibExcludedDirs) + @("__pycache__")) `
        -ExcludeFiles @("turtle.py", "*.pyc", "*.pyo")
}
$sitePackagesDir = Join-Path $outLib "site-packages"
New-Item -ItemType Directory -Force -Path $sitePackagesDir | Out-Null

# Do not ship python._pth — it enables embed isolation and breaks a portable Lib/ layout.
Get-ChildItem -Path $OutputDir -Filter "python$Ver._pth" -ErrorAction SilentlyContinue | Remove-Item -Force

if (-not (Test-Path $RuntimeRequirements)) {
    throw "Missing locked runtime requirements: $RuntimeRequirements"
}

Write-Host "Installing graf-id and dependencies into runtime..."
$SitePackages = Join-Path $OutputDir "Lib\site-packages"
Initialize-VenvBuildEnvironment
if ($UpgradePip) {
    & $VenvPython -m pip install --upgrade pip -q
}
& $VenvPython -m pip install -r $RuntimeRequirements --target $SitePackages --no-deps --upgrade -q
# pip --target drops console-script launchers into bin/. They hard-code the build
# machine's .venv interpreter path and cannot work in an installed app, so they
# are build leftovers (the packages themselves stay importable).
$scriptLaunchers = Join-Path $SitePackages "bin"
if (Test-Path $scriptLaunchers) {
    Remove-Item -Recurse -Force $scriptLaunchers
}
# Some wheels (e.g. colorama) ship their own test suites inside the package.
Get-ChildItem -Path $SitePackages -Recurse -Directory -Force |
    Where-Object { $_.Name -in @("test", "tests") } |
    Sort-Object { $_.FullName.Length } -Descending |
    ForEach-Object { if (Test-Path $_.FullName) { Remove-Item -Recurse -Force $_.FullName } }
if (Test-Path "$SitePackages\grafid") {
    Remove-Item -Recurse -Force "$SitePackages\grafid"
}
# Application code only: no tests, no developer bytecode (a dev .venv on another
# Python minor version leaves e.g. cpython-314 caches here), and no VCS metadata
# (a stray nested .git / .gitattributes inside grafid/ must never be shipped).
Copy-Tree -Source (Join-Path $RepoRoot "grafid") -Destination "$SitePackages\grafid" `
    -ExcludeDirs @((Join-Path $RepoRoot "grafid\tests"), "__pycache__", ".git") `
    -ExcludeFiles @("*.pyc", "*.pyo", ".gitattributes", ".gitignore")

$RuntimePython = Join-Path $OutputDir "python.exe"
if (-not (Test-Path $RuntimePython)) {
    throw "runtime/python.exe was not created"
}

# Bytecode: drop every cache that exists (pip --target compiles timestamp-based
# caches at install time) and regenerate ALL of it with the runtime's own
# pinned interpreter. The app lives under Program Files where Python cannot
# write __pycache__ at run time, so shipping complete bytecode keeps start-up
# fast. unchecked-hash makes the .pyc files independent of file timestamps
# (installers do not always preserve them) and byte-for-byte reproducible;
# -s/-p keep the build machine's path out of the bytecode.
Write-Host "Compiling bytecode with the pinned runtime interpreter..."
Get-ChildItem -Path $OutputDir -Recurse -Directory -Filter "__pycache__" -Force |
    Remove-Item -Recurse -Force
$savedPyEnv = @{}
foreach ($name in @("PYTHONHOME", "PYTHONPATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE")) {
    $savedPyEnv[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
    Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
}
$env:PYTHONNOUSERSITE = "1"
try {
    $reportedVersion = (& $RuntimePython -c "import platform; print(platform.python_version())").Trim()
    if ($reportedVersion -ne $RequiredPythonVersion) {
        throw "Runtime interpreter reports Python $reportedVersion, expected $RequiredPythonVersion"
    }
    & $RuntimePython -m compileall -q -f -j 0 --invalidation-mode unchecked-hash `
        -s $OutputDir -p "runtime" (Join-Path $OutputDir "Lib")
    if ($LASTEXITCODE -ne 0) {
        throw "Bytecode compilation failed (compileall exit code $LASTEXITCODE)"
    }
} finally {
    foreach ($name in $savedPyEnv.Keys) {
        if ($null -eq $savedPyEnv[$name]) {
            Remove-Item -Path "Env:$name" -ErrorAction SilentlyContinue
        } else {
            Set-Item -Path "Env:$name" -Value $savedPyEnv[$name]
        }
    }
}

Write-Host "Verifying embedded imports..."
$prevPP = $env:PYTHONPATH
$env:PYTHONPATH = $SitePackages
$env:PYTHONNOUSERSITE = "1"
# Verification must not add any bytecode of its own to the runtime.
$env:PYTHONDONTWRITEBYTECODE = "1"
Push-Location $OutputDir
try {
    & $RuntimePython -c "import encodings; import grafid; import typer; assert typer.__version__ == '0.25.1'; print('ok', grafid.__file__, typer.__version__)"
    if ($LASTEXITCODE -ne 0) {
        throw "Embedded runtime verification failed"
    }
    $pyprojectText = Get-Content (Join-Path $RepoRoot "pyproject.toml") -Raw
    if ($pyprojectText -notmatch '(?m)^version\s*=\s*"([^"]+)"') {
        throw "Could not read the project version from pyproject.toml"
    }
    $expectedVersion = $Matches[1]
    $shippedVersion = (& $RuntimePython -c "import grafid; print(grafid.__version__)").Trim()
    if ($shippedVersion -ne $expectedVersion) {
        throw "Bundled grafid reports version $shippedVersion, expected $expectedVersion (pyproject.toml)"
    }
    Write-Host "grafid.__version__ = $shippedVersion"
} finally {
    Pop-Location
    $env:PYTHONPATH = $prevPP
    Remove-Item Env:PYTHONNOUSERSITE -ErrorAction SilentlyContinue
    Remove-Item Env:PYTHONDONTWRITEBYTECODE -ErrorAction SilentlyContinue
}

# Final payload audit: fail the build instead of shipping tests, dev leftovers
# or a second Python's bytecode.
Write-Host "Auditing runtime payload..."
$violations = New-Object System.Collections.Generic.List[string]
$forbiddenDirs = @(
    "Lib\test", "Lib\idlelib", "Lib\tkinter", "Lib\turtledemo", "Lib\ensurepip",
    "Lib\lib2to3", "Lib\venv", "Lib\pydoc_data", "Lib\msilib",
    "Lib\site-packages\grafid\tests", "Lib\site-packages\grafid\.git", "Lib\site-packages\bin"
)
foreach ($rel in $forbiddenDirs) {
    if (Test-Path (Join-Path $OutputDir $rel)) { $violations.Add("forbidden directory shipped: $rel") }
}
Get-ChildItem -Path $OutputDir -Recurse -Directory -Force |
    Where-Object { $_.Name -in @("test", "tests", "idle_test") } |
    ForEach-Object { $violations.Add("test directory shipped: $($_.FullName.Substring($OutputDir.Length + 1))") }
foreach ($rel in @("Lib\turtle.py", "DLLs\_tkinter.pyd", "DLLs\tcl86t.dll", "DLLs\tk86t.dll", "DLLs\_ctypes_test.pyd")) {
    if (Test-Path (Join-Path $OutputDir $rel)) { $violations.Add("forbidden file shipped: $rel") }
}
Get-ChildItem -Path (Join-Path $OutputDir "DLLs") -Filter "_test*.pyd" -ErrorAction SilentlyContinue |
    ForEach-Object { $violations.Add("test extension module shipped: DLLs\$($_.Name)") }
if (-not (Test-Path (Join-Path $OutputDir "LICENSE-PYTHON.txt"))) { $violations.Add("missing license: LICENSE-PYTHON.txt") }
$expectedTag = "cpython-$Ver"
Get-ChildItem -Path $OutputDir -Recurse -File -Filter "*.pyc" -Force | ForEach-Object {
    if ($_.Name -notlike "*.$expectedTag.pyc") {
        $violations.Add("bytecode for another Python: $($_.FullName.Substring($OutputDir.Length + 1))")
    }
}
Get-ChildItem -Path $OutputDir -Filter "python*.dll" -File | ForEach-Object {
    if ($_.Name -ne "python$Ver.dll" -and $_.Name -ne "python3.dll") {
        $violations.Add("unexpected interpreter library: $($_.Name)")
    }
}
$grafidShipped = Join-Path $SitePackages "grafid"
Get-ChildItem -Path $grafidShipped -Recurse -File -Force | ForEach-Object {
    if ($_.Extension -notin @(".py", ".pyc")) {
        $violations.Add("non-code file inside shipped grafid: $($_.FullName.Substring($OutputDir.Length + 1))")
    }
}
if ($violations.Count -gt 0) {
    throw ("Runtime payload audit failed:`n  " + ($violations -join "`n  "))
}

Write-Host "Runtime build complete."
