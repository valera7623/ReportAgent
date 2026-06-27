# Деплой (администратор)

Краткое руководство по развёртыванию ReportAgent на VPS.

## Режимы

| Режим | `TRAEFIK_ENABLED` | Когда использовать |
|-------|-------------------|-------------------|
| **Traefik** | `true` | ReportAgent владеет портами 80/443 |
| **Standalone** | `false` | Порты заняты (SMDG nginx), API на `:8000` |

## Быстрый деплой

```bash
cp .env.example .env
# Отредактируйте DOMAIN, SMTP, OPENAI_API_KEY, ...

docker network create traefik_network 2>/dev/null || true
mkdir -p app/data storage/pdfs storage/uploads logs traefik/acme
chmod +x deploy.sh scripts/build-docs.sh
./scripts/build-docs.sh   # документация /help/
./deploy.sh
```

## Проверка

```bash
# Traefik mode
curl https://ваш-домен/health
curl https://ваш-домен/help/

# Standalone mode (изнутри Docker)
docker exec reportagent_fastapi curl -s http://localhost:8000/health
```

## Автогенерация секретов

`deploy.sh` автоматически генерирует:

- `GRAFANA_ADMIN_PASSWORD` — если пустой
- `ADMIN_API_KEY` — если placeholder `change-me-generate-on-deploy`

## GitHub Actions

Push в `main`/`master` → CI + SSH-деплой. См. [CI/CD](../deployment/ci-cd.md).

## Подробнее

- [Docker](../deployment/docker.md)
- [VPS](../deployment/vps.md)
- [Переменные окружения](../deployment/environment-variables.md)
