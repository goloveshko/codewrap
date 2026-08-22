$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "🔨 Building CodeWrap package in: $ProjectRoot" -ForegroundColor Cyan
uv build

Write-Host "🚀 Installing CodeWrap globally in editable mode..." -ForegroundColor Green
uv tool install --editable . --force

Write-Host "✅ Success! CodeWrap is ready to use:" -ForegroundColor Yellow
codewrap -h