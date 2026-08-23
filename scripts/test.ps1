$PSScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

Write-Host "🔍 1/5. Running Ruff Linter..." -ForegroundColor Cyan
uv run ruff check .
if ($LASTEXITCODE -ne 0) { 
    Write-Host "❌ Ruff Check Failed!" -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "🎨 2/5. Checking Code Formatting..." -ForegroundColor Cyan
uv run ruff format --check .
if ($LASTEXITCODE -ne 0) { 
    Write-Host "❌ Ruff Format Check Failed! Run 'uv run ruff format .' to fix." -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "🧪 3/5. Running Mypy Type Checker..." -ForegroundColor Cyan
uv run mypy src
if ($LASTEXITCODE -ne 0) { 
    Write-Host "❌ Mypy Type Check Failed!" -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "🚦 4/5. Running Pytest Suite..." -ForegroundColor Cyan
uv run pytest
if ($LASTEXITCODE -ne 0) { 
    Write-Host "❌ Pytest Suite Failed!" -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "📦 5/5. Testing Package Build..." -ForegroundColor Cyan
uv build
if ($LASTEXITCODE -ne 0) { 
    Write-Host "❌ Package Build Failed!" -ForegroundColor Red
    exit $LASTEXITCODE 
}

Write-Host "`n✅ All Quality Checks & Tests Passed Successfully! Ready for Release!" -ForegroundColor Green