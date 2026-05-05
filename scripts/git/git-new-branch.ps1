Write-Host "========================================="
Write-Host "Criar nova branch a partir da main"
Write-Host "========================================="
Write-Host ""

if (-not (Test-Path ".git")) {
    Write-Host "Erro: este diretorio nao e um repositorio Git."
    exit 1
}

$status = git status --porcelain

if (-not [string]::IsNullOrWhiteSpace($status)) {
    Write-Host "Erro: existem alteracoes nao commitadas."
    Write-Host "Faça commit ou stash antes de criar nova branch."
    git status
    exit 1
}

$branchName = Read-Host "Digite o nome da nova branch"

if ([string]::IsNullOrWhiteSpace($branchName)) {
    Write-Host "Erro: nome da branch invalido."
    exit 1
}

Write-Host ""
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
Write-Host "Criando branch $branchName..."
git checkout -b $branchName

if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao criar branch $branchName."
    exit 1
}

Write-Host ""
Write-Host "Branch criada com sucesso: $branchName"