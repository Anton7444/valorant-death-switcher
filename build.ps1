$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project '.venv-official\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = Join-Path $project '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw '未找到 .venv；請按 README 安裝依賴。'
}
Push-Location $project
try {
    & $python -m PyInstaller --noconfirm 'ValorantDeathSwitcher.spec'
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller 打包失敗。' }
    Write-Host "程式位於：$project\dist\ValorantDeathSwitcher\ValorantDeathSwitcher.exe"
}
finally {
    Pop-Location
}
