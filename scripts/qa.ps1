Write-Host "🔧 Formatando com ruff..."
ruff format .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "🔍 Corrigindo com ruff check..."
ruff check . --fix
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "🎨 Formatando com black..."
black .
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "🧪 Rodando testes..."
pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "✅ Tudo finalizado com sucesso!"