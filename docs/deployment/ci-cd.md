# CI/CD

GitHub Actions workflows в `.github/workflows/`.

## Workflows

| Workflow | Триггер | Назначение |
|----------|---------|------------|
| `ci.yml` | Pull Request → main | Тесты, compileall, docker config |
| `deploy-vps.yml` | Push → main, workflow_dispatch | CI + SSH-деплой |

## Secrets (GitHub Actions)

| Secret | Описание |
|--------|----------|
| `VPS_HOST` | IP или домен VPS |
| `VPS_USER` | SSH-пользователь |
| `VPS_SSH_PRIVATE_KEY` | Приватный SSH-ключ |
| `VPS_PORT` | SSH-порт (опционально) |
| `GIT_DEPLOY_TOKEN` | PAT для приватного репо |

## Variables

| Variable | Пример |
|----------|--------|
| `DEPLOY_PATH` | `~/ReportAgent` |
| `DOMAIN` | `reportagent.fileguardian.info` |
| `SKIP_EXTERNAL_HEALTH_CHECK` | `true` |

## Поток деплоя

```
push main → CI → SSH VPS → git pull → build-docs → deploy.sh
```

## Первый деплой на VPS

```bash
mkdir -p app/data storage/pdfs storage/uploads logs
cp .env.example .env && nano .env
```

Push в `main` — workflow задеплоит автоматически.

## Что не синхронизируется через git

| Путь | Примечание |
|------|------------|
| `.env` | Секреты |
| `app/data/*.db` | SQLite |
| `storage/`, `logs/` | Runtime |

## Документация

MkDocs site (`site/`) коммитится в репозиторий после сборки (как в MedInsight).

Локально:

```bash
./scripts/build-docs.sh
mkdocs serve   # preview at :8000
```
