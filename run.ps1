$ErrorActionPreference = 'Stop'
$project = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $project '.venv-official\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    $python = Join-Path $project '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $python)) {
    throw '未找到 .venv；請按 README 安裝依賴。'
}
& $python (Join-Path $project 'run.py')
