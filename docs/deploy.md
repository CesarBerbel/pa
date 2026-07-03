# Deploy em produção

Comandos para atualizar e subir os projetos em produção via Docker Compose.

## PA (este projeto)

```bash
cd /opt/pa && git pull && docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
```

## Pocket

```bash
cd /opt/pocket && git pull && docker compose -f docker-compose.prod.yml up -d --build
```

## O que cada comando faz

1. `cd` até a pasta do projeto no servidor.
2. `git pull` — traz as últimas alterações da branch atual.
3. `docker compose ... up -d --build` — reconstrói as imagens alteradas e sobe os containers atualizados em background (`-d`).

No caso do PA, `--env-file .env.prod` aponta explicitamente para o arquivo de variáveis de ambiente de produção (diferente do `.env` local de desenvolvimento).
