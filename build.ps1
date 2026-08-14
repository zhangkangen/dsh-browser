<#
.SYNOPSIS
One-click build for dsh-browser: kill leftover processes -> PyInstaller -> copy node runtime -> verify -> optional Inno Setup package.

Usage:
  .\build.ps1                  # build dist\dsh-browser only
  .\build.ps1 -Installer       # build and produce installer\dsh-browser-setup.exe
  .\build.ps1 -InstallDeps     # run pip install -r requirements.txt first
  .\build.ps1 -Python py3.13   # python executable to use (default "python")

Exit code: 0 success, 1 failure.
#>
param(
    [switch]$Installer,
    [switch]$InstallDeps,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

function Die([string]$msg) {
    Write-Host "[build] FAILED: $msg" -ForegroundColor Red
    exit 1
}

Write-Host "[build] Killing leftover dsh-browser processes (avoid locked DLLs in dist)..."
Get-Process -Name dsh-browser -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Milliseconds 500

if ($InstallDeps) {
    Write-Host "[build] Installing dependencies..."
    & $Python -m pip install -r (Join-Path $root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Die "pip install failed" }
}

Write-Host "[build] Checking build deps (webview/pythonnet)..."
& $Python -c "import webview, pythonnet"
if ($LASTEXITCODE -ne 0) {
    Die "pywebview/pythonnet missing. Run: .\build.ps1 -InstallDeps or pip install -r requirements.txt"
}

Write-Host "[build] PyInstaller building..."
& $Python -m PyInstaller (Join-Path $root "dsh-browser.spec") `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "build") `
    --noconfirm
if ($LASTEXITCODE -ne 0) { Die "PyInstaller build failed (see log above)" }

$nodeSrc = Join-Path $root "bundle\node"
$nodeDst = Join-Path $root "dist\dsh-browser\node"
if (-not (Test-Path $nodeSrc)) { Die "Offline runtime source not found: $nodeSrc" }
Write-Host "[build] Copying node runtime -> $nodeDst ..."
robocopy $nodeSrc $nodeDst /E /IS /IT /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -ge 8) { Die "robocopy failed to copy node runtime" }

$nodeExe = Join-Path $nodeDst "node.exe"
$dshJs = Join-Path $nodeDst "node_modules\@deepseek-ai\dsh\lib\bin.js"
if (-not (Test-Path $nodeExe)) { Die "verify failed: missing $nodeExe" }
if (-not (Test-Path $dshJs)) { Die "verify failed: missing $dshJs" }

if ($Installer) {
    $version = (Get-Content (Join-Path $root "version.txt") -Raw).Trim()
    $iscc = Get-Command iscc -ErrorAction SilentlyContinue
    $isccPath = $null
    if ($iscc) {
        $isccPath = $iscc.Source
    } else {
        $candidate = Join-Path ${env:ProgramFiles(x86)} "Inno Setup 6\ISCC.exe"
        if (Test-Path $candidate) { $isccPath = $candidate }
    }
    if (-not $isccPath) { Die "Inno Setup 6 (ISCC.exe) not found; dist built only" }
    Write-Host "[build] Inno Setup packaging v$version ..."
    & $isccPath (Join-Path $root "installer.iss") /DMyAppVersion=$version
    if ($LASTEXITCODE -ne 0) { Die "Inno Setup packaging failed" }
    Write-Host "[build] DONE: $root\installer\dsh-browser-setup.exe" -ForegroundColor Green
} else {
    Write-Host "[build] DONE: $root\dist\dsh-browser" -ForegroundColor Green
}