# AeroGuard Windows executable build script (PyInstaller 6.x, Python 3.12)
#
# Usage:
#   python -m pip install --user pyinstaller
#   powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1        # single combined exe
#   powershell -ExecutionPolicy Bypass -File tools\build_exe.ps1 -All  # four separate exes
#
# Default output (single file, console subsystem, GUI hides own console):
#   .\dist\AeroGuard.exe
#     double-click            -> desktop GUI
#     AeroGuard.exe scan ...  -> scan / JSON report CLI
#     AeroGuard.exe manage .. -> addon management CLI (incl. note-*)
#     AeroGuard.exe history . -> history / baseline CLI
#
# With -All, additionally keeps the legacy four standalone exes in dist\.
# Single-file exes are large (~12 MB) and first launch unpacks slowly.

param(
    [switch]$All
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $Root
try {
    $python = "python"

    function Invoke-PyInstaller($Name, $Script, [bool]$Windowed) {
        Write-Host ("==> building " + $Name + " ...")
        $windowed = "--windowed"
        if (-not $Windowed) { $windowed = "--console" }
        & $python -m PyInstaller --noconfirm --clean --onefile $windowed `
            --name $Name `
            --version-file (Join-Path $Root "tools\version_info.txt") `
            --distpath (Join-Path $Root "dist") `
            --workpath (Join-Path $Root "build") `
            --specpath (Join-Path $Root "build") `
            (Join-Path $Root $Script)
        if ($LASTEXITCODE -ne 0) {
            throw ("build failed for " + $Name + " (exit " + $LASTEXITCODE + ")")
        }
    }

    # 默认：单个 AeroGuard.exe（launcher 分发 GUI + 三个 CLI）
    Invoke-PyInstaller "AeroGuard" "launcher.py" $false

    if ($All) {
        Invoke-PyInstaller "aeroguard"         "main.py"        $false
        Invoke-PyInstaller "aeroguard-manage"  "manage.py"      $false
        Invoke-PyInstaller "aeroguard-history" "history_cli.py" $false
    }

    Write-Host ""
    Write-Host "Artifacts in dist/:"
    Get-ChildItem (Join-Path $Root "dist") -Filter *.exe |
        Select-Object Name, @{n="MB"; e={[math]::Round($_.Length / 1MB, 1)}} |
        Format-Table -AutoSize
}
finally {
    Pop-Location
}
