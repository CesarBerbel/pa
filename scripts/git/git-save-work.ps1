Write-Host "========================================="
Write-Host "Salvar trabalho atual"
Write-Host "========================================="
Write-Host ""

if (-not (Test-Path ".git")) {
    Write-Host "Erro: este diretorio nao e um repositorio Git."
    exit 1
}

$currentBranch = git branch --show-current

if ([string]::IsNullOrWhiteSpace($currentBranch)) {
    Write-Host "Erro: nao foi possivel identificar a branch atual."
    exit 1
}

Write-Host "Branch atual: $currentBranch"
Write-Host ""

git status

Write-Host ""
$confirm = Read-Host "Deseja adicionar todos os arquivos alterados? Digite S para confirmar"

if ($confirm -ne "S" -and $confirm -ne "s") {
    Write-Host "Operacao cancelada."
    exit 0
}

git add .

if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao executar git add."
    exit 1
}

$commitMessage = Read-Host "Digite a mensagem do commit"

if ([string]::IsNullOrWhiteSpace($commitMessage)) {
    Write-Host "Erro: mensagem do commit invalida."
    exit 1
}

git commit -m "$commitMessage"

if ($LASTEXITCODE -ne 0) {
    Write-Host "Erro ao criar commit."
    exit 1
}

Write-Host ""
$pushConfirm = Read-Host "Deseja enviar para o remoto agora? Digite S para confirmar"

if ($pushConfirm -eq "S" -or $pushConfirm -eq "s") {
    git push origin $currentBranch

    if ($LASTEXITCODE -ne 0) {
        Write-Host "Erro ao executar push."
        exit 1
    }

    Write-Host ""
    Write-Host "Commit enviado com sucesso."
} else {
    Write-Host ""
    Write-Host "Commit criado localmente. Push nao executado."
}