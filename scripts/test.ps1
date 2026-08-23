$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "🔍 1/4. Running Ruff Linter..." -ForegroundColor Cyan
uv run ruff check .
if ($LASTEXITCODE -ne 0) { 
    Write-Host "❌ Ruff Check Failed!" -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "🎨 2/4. Checking Code Formatting..." -ForegroundColor Cyan
uv run ruff format --check .
if ($LASTEXITCODE -ne 0) { 
    Write-Host "❌ Ruff Format Check Failed! Run 'uv run ruff format .' to fix." -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "🧪 3/4. Running Mypy Type Checker..." -ForegroundColor Cyan
uv run mypy src
if ($LASTEXITCODE -ne 0) { 
    Write-Host "❌ Mypy Type Check Failed!" -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "📦 4/4. Testing Package Build..." -ForegroundColor Cyan
uv build
if ($LASTEXITCODE -ne 0) { 
    Write-Host "❌ Package Build Failed!" -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "`n✅ All Quality Checks Passed Successfully! Ready for Release!" -ForegroundColor Green