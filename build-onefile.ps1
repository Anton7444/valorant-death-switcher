$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project '.venv-official\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = Join-Path $project '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw '未找到 Python 虛擬環境；請按 README 安裝依賴。'
}
Push-Location $project
try {
    & $python -m PyInstaller --noconfirm --distpath dist-onefile --workpath build-onefile 'ValorantDeathSwitcherOneFile.spec'
    if ($LASTEXITCODE -ne 0) { throw '單檔案程式打包失敗。' }
    Write-Host "單檔案程式位於：$project\dist-onefile\ValorantDeathSwitcherStandalone.exe"
}
finally {
    Pop-Location
}
