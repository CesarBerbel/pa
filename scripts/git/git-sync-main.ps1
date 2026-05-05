Write-Host "========================================="
Write-Host "Sincronizando branch main"
Write-Host "========================================="
Write-Host ""

if (-not (Test-Path ".git")) {
    Write-Host "Erro: este diretorio nao e um repositorio Git."
    exit 1
}

$status = git status --porcelain

if (-not [string]::IsNullOrWhiteSpace($status)) {
    Write-Host "Erro: existem alteracoes nao commitadas."
    Write-Host "Faça commit ou stash antes de sincronizar a main."
    git status
    exit 1
}

Write-Host "Mudando para main..."
git checkout main

if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao mudar para main."
    exit 1
}

Write-Host "Atualizando main..."
git pull origin main

if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao atualizar main."
    exit 1
}

Write-Host ""
Write-Host "Main sincronizada com sucesso."