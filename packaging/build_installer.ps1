# 构建 Windows 单文件安装器（NSIS）
# 用法：powershell -ExecutionPolicy Bypass -File packaging\build_installer.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$makensis = "D:\NSIS\makensis.exe"
if (-not (Test-Path $makensis)) {
    $makensis = "C:\Program Files (x86)\NSIS\makensis.exe"
}
if (-not (Test-Path $makensis)) {
    throw "未找到 makensis.exe（NSIS 3）"
}

if (-not (Test-Path (Join-Path $root "dist\SealBox\SealBox.exe"))) {
    Write-Host "未发现 dist\SealBox，先构建应用……"
    & python (Join-Path $root "packaging\build.py")
    if ($LASTEXITCODE -ne 0) { throw "应用构建失败" }
}

$nsi = Join-Path $root "packaging\installer\SealBox.nsi"
Write-Host "编译安装器：$nsi"
& $makensis /V2 "/DSRCDIR=$root" $nsi
if ($LASTEXITCODE -ne 0) { throw "NSIS 编译失败（退出码 $LASTEXITCODE）" }

$setup = Join-Path $root "dist\SealBoxSetup-0.1.0.exe"
if (-not (Test-Path $setup)) { throw "未生成安装器：$setup" }
$hash = (Get-FileHash $setup -Algorithm SHA256).Hash.ToLower()
$size = [math]::Round((Get-Item $setup).Length / 1MB, 1)
Write-Host ""
Write-Host "安装器：$setup"
Write-Host "大小：$size MB"
Write-Host "SHA-256：$hash"
