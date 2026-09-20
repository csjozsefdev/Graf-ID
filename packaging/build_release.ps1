# Full Windows release build: embedded runtime + Tauri bundle.
$ErrorActionPreference = "Stop"

$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $RepoRoot

& (Join-Path $PSScriptRoot "create_icons.ps1")
& (Join-Path $PSScriptRoot "build_runtime.ps1")
& (Join-Path $PSScriptRoot "verify_packaged_runtime.ps1")

# Tauri's bundle.resources copy (desktop/src-tauri/runtime/ -> target/release/runtime/)
# overwrites existing files but never deletes ones no longer present in the
# source — so a target/release/runtime/ left over from a previous build with
# a different Python version keeps stale stdlib files (e.g. an old pathlib/
# package directory) alongside the freshly copied ones, breaking the
# packaged interpreter with an internal ImportError. Found the hard way
# rebuilding for the 3.12.10 pin after target/release/ had accumulated
# builds since June.
#
# The clean-up now lives in build_runtime.ps1 (which is ALSO tauri.conf.json's
# beforeBuildCommand), so this script and a bare `npm run tauri:build` both start
# from an empty target\release\runtime and target\release\bundle. Below, the
# result is checked against the freshly built runtime as a second line of defence.
$StagedRuntime = Join-Path $RepoRoot "desktop\src-tauri\runtime"
$BundledRuntime = Join-Path $RepoRoot "desktop\src-tauri\target\release\runtime"

Set-Location (Join-Path $RepoRoot "desktop")
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    throw "npm not found. Install Node.js to run tauri build."
}

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "cargo not found. Install Rust (rustup) to run tauri build."
}

npm install
npm run tauri:build
if ($LASTEXITCODE -ne 0) {
    throw "tauri build failed with exit code $LASTEXITCODE"
}

$BundleRoot = Join-Path $RepoRoot "desktop\src-tauri\target\release\bundle"
$ReleaseExe = Join-Path $RepoRoot "desktop\src-tauri\target\release\graf-id-desktop.exe"
if (-not (Test-Path $ReleaseExe)) {
    throw "Missing release binary: $ReleaseExe"
}
if (-not (Test-Path $BundleRoot)) {
    throw "Missing bundle directory: $BundleRoot"
}

# The runtime Tauri bundled must be exactly the freshly built one: same files,
# same sizes, nothing left over from an earlier build.
function Get-RuntimeManifest($root) {
    Get-ChildItem -Path $root -Recurse -File -Force |
        ForEach-Object { "{0}|{1}" -f $_.FullName.Substring($root.Length + 1), $_.Length } |
        Sort-Object
}
$staged = @(Get-RuntimeManifest $StagedRuntime)
$bundled = @(Get-RuntimeManifest $BundledRuntime)
$drift = Compare-Object -ReferenceObject $staged -DifferenceObject $bundled
if ($drift) {
    $sample = ($drift | Select-Object -First 10 | ForEach-Object { "$($_.SideIndicator) $($_.InputObject)" }) -join "`n  "
    throw "Bundled runtime differs from the freshly built runtime ($($drift.Count) differences):`n  $sample"
}
Write-Host "Bundled runtime matches the freshly built runtime ($($staged.Count) files)."

& (Join-Path $PSScriptRoot "verify_release_bundle.ps1")

Write-Host "Release build finished."
Write-Host "  Binary: $ReleaseExe"
Write-Host "  Bundle: $BundleRoot"
