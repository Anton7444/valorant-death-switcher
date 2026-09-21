$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project '.venv-official\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = Join-Path $project '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw '未找到 Python 虚拟环境；请按 README 安装依赖。'
}
Push-Location $project
try {
    & $python -m PyInstaller --noconfirm --distpath dist-onefile --workpath build-onefile 'ValorantDeathSwitcherOneFile.spec'
    if ($LASTEXITCODE -ne 0) { throw '单文件程序打包失败。' }
    Write-Host "单文件程序位于：$project\dist-onefile\ValorantDeathSwitcherStandalone.exe"
}
finally {
    Pop-Location
}
