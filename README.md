# ReportAgent

Micro-SaaS for generating PDF reports with charts from CSV/Excel uploads or public Google Sheets. Reports are delivered by email via SMTP.

## Architecture

```
Client → Traefik (TLS) → FastAPI → Celery → Redis
                              ↓
                    parser → analyst → visualizer → sender (PDF + SMTP)
```

| Service        | Role                                      |
|----------------|-------------------------------------------|
| **fastapi**    | HTTP API (`POST /generate_report`)        |
| **celery_worker** | Background report pipeline             |
| **redis**      | Celery broker & result backend            |
| **traefik**    | Reverse proxy, Let's Encrypt SSL          |

## Quick start (local development — WSL / laptop)

Без Traefik, без pull образа proxy. API сразу на **http://localhost:8000/docs**.

```bash
cp .env.example .env
chmod +x deploy-dev.sh scripts/healthcheck_celery.sh scripts/pull-images.sh
./deploy-dev.sh
```

Если Docker Hub недоступен, в `.env` укажите зеркало Redis:

```bash
REDIS_IMAGE=public.ecr.aws/docker/library/redis:7-alpine
```

## Production (VPS + Traefik)

```bash
cp .env.example .env   # DOMAIN, SMTP, LETSENCRYPT_EMAIL
docker network create traefik_network || true
chmod +x deploy.sh
./deploy.sh
```

## GitHub Actions — автодеплой на VPS

Workflows в `.github/workflows/`:

| Workflow | Триггер | Назначение |
|----------|---------|------------|
| `ci.yml` | Pull Request → `main` | Тесты, `compileall`, `docker compose config`, сборка образа |
| `deploy-vps.yml` | Push → `main`, `workflow_dispatch` | CI + SSH-деплой на VPS |

### Однократная подготовка VPS

```bash
# Docker + compose (если ещё нет)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # перелогиниться

# Сеть Traefik
docker network create traefik_network 2>/dev/null || true

# SSH-ключ для GitHub Actions (на вашем ПК)
ssh-keygen -t ed25519 -C "github-actions-reportagent" -f ~/.ssh/reportagent_deploy
ssh-copy-id -i ~/.ssh/reportagent_deploy.pub ubuntu@YOUR_VPS_IP
```

Публичный ключ пользователя VPS должен быть в `~/.ssh/authorized_keys`.  
Приватный ключ `reportagent_deploy` — в GitHub Secret `VPS_SSH_PRIVATE_KEY`.

### Secrets (Settings → Secrets and variables → Actions)

| Secret | Пример | Описание |
|--------|--------|----------|
| `VPS_HOST` | `203.0.113.10` | IP или домен VPS |
| `VPS_USER` | `ubuntu` | SSH-пользователь |
| `VPS_SSH_PRIVATE_KEY` | содержимое `reportagent_deploy` | Приватный SSH-ключ |
| `VPS_PORT` | `22` | SSH-порт (опционально) |
| `GIT_DEPLOY_TOKEN` | GitHub PAT | Только для **приватного** репозитория (`repo` scope) |

### Variables (не секреты)

| Variable | Пример | Описание |
|----------|--------|----------|
| `DEPLOY_PATH` | `/opt/ReportAgent` | Путь на VPS (по умолчанию `/opt/ReportAgent`) |
| `DOMAIN` | `reports.example.com` | Для health-check после деплоя |

### Environment `production`

Создайте environment **production** в GitHub (Settings → Environments) — можно включить manual approval перед деплоем.

### Первый автодеплой

1. На VPS вручную создайте `.env` **или** дождитесь первого клона и выполните:
   ```bash
   sudo mkdir -p /opt/ReportAgent
   sudo chown $USER:$USER /opt/ReportAgent
   ```
2. Запушьте в `main` — workflow клонирует репо, создаст `.env` не будет (нужен вручную на сервере):
   ```bash
   # на VPS после первого деплоя / вручную до него:
   cp .env.example .env && nano .env
   mkdir -p storage/pdfs storage/uploads logs traefik/acme
   touch traefik/acme/acme.json && chmod 600 traefik/acme/acme.json
   ```
3. Повторный push в `main` или **Actions → Deploy to VPS → Run workflow**.

Ручной запуск: Actions → **Deploy to VPS** → Run workflow.

## Деплой на VPS (вручную)

Требования: **Ubuntu 22.04+**, Docker и Docker Compose plugin установлены, DNS A-запись домена указывает на IP сервера.

### 1. Клонирование

```bash
git clone <your-repo-url> ReportAgent
cd ReportAgent
```

### 2. Настройка окружения

```bash
cp .env.example .env
nano .env
```

Обязательно заполните:

| Переменная          | Описание                              |
|---------------------|---------------------------------------|
| `DOMAIN`            | Ваш домен, например `reports.example.com` |
| `LETSENCRYPT_EMAIL` | Email для Let's Encrypt               |
| `SMTP_HOST`         | SMTP-сервер                           |
| `SMTP_PORT`         | Обычно `587`                          |
| `SMTP_USER`         | Логин SMTP                            |
| `SMTP_PASSWORD`     | Пароль SMTP                           |
| `SMTP_FROM`         | Адрес отправителя                     |
| `SECRET_KEY`        | Случайная строка                      |

Для тестирования SSL без лимитов Let's Encrypt раскомментируйте staging CA в `.env`:

```bash
ACME_CA_SERVER=https://acme-staging-v02.api.letsencrypt.org/directory
```

### 3. Подготовка директорий и сети

```bash
docker network create traefik_network 2>/dev/null || true
mkdir -p storage/pdfs storage/uploads logs traefik/acme
touch traefik/acme/acme.json
chmod 600 traefik/acme/acme.json
chmod +x deploy.sh scripts/healthcheck_celery.sh
```

### 4. Запуск

```bash
./deploy.sh
```

Скрипт автоматически:

- создаёт сеть `traefik_network` (если нет);
- загружает переменные из `.env`;
- собирает образы;
- останавливает старые контейнеры (`down --remove-orphans`);
- поднимает стек (`up -d`);
- чистит dangling-образы;
- выводит статус контейнеров.

### 5. Проверка

1. Откройте `https://ваш-домен/docs` — должен открыться Swagger UI.
2. `GET /health` → `{"status":"ok"}`.
3. Скачайте тестовый CSV: `GET /samples/sample_sales.csv` (или `samples/sample_sales.csv` в репозитории).
4. Отправьте через `POST /generate_report`:
   - `file` — CSV или Excel (без email, если хотите только скачать PDF);
   - `email` — опционально, для доставки на почту.
5. Следите за воркером:

```bash
docker logs -f reportagent_celery_worker
```

6. Проверьте статус задачи:

```bash
curl https://ваш-домен/tasks/<task_id>
```

7. Скачайте PDF без email:

```bash
curl -OJ https://ваш-домен/tasks/<task_id>/pdf
```

8. Если указан `email` — PDF также придёт на почту. Файл сохраняется в `storage/pdfs/<task_id>/`.

### Быстрый тест без Swagger

```bash
# Без email — только скачивание PDF
TASK_ID=$(curl -s -X POST "https://ваш-домен/generate_report" \
  -F "file=@samples/sample_sales.csv" | jq -r .task_id)

# Подождать ~10 сек, затем:
curl -OJ "https://ваш-домен/tasks/${TASK_ID}/pdf"
```

## API

### `POST /generate_report`

Multipart form:

| Field        | Type   | Required | Description                    |
|--------------|--------|----------|--------------------------------|
| `file`       | file   | no*      | CSV, `.xlsx`, `.xls`           |
| `sheets_url` | string | no*      | Public Google Sheets URL       |
| `email`      | string | no       | Опционально — доставка PDF на почту |

\* Укажите **либо** `file`, **либо** `sheets_url`.

**Response** `202`:

```json
{
  "task_id": "abc-123",
  "status": "queued",
  "message": "Report generation started. Download at GET /tasks/abc-123/pdf when ready.",
  "download_url": "/tasks/abc-123/pdf"
}
```

### `GET /tasks/{task_id}`

Проверка статуса Celery-задачи. При `SUCCESS` в `result` есть `download_url`.

### `GET /tasks/{task_id}/pdf`

Скачивание готового PDF. Возвращает `202`, если отчёт ещё генерируется.

### `GET /samples/sample_sales.csv`

Тестовый CSV с продажами (числовые и категориальные колонки для графиков).

### `GET /health`

Healthcheck для Docker и Traefik.

## Agents

| Agent              | File                    | Log file              |
|--------------------|-------------------------|-----------------------|
| `agent_parser`     | `app/agents/parser.py`  | `logs/log_parser.log` |
| `agent_analyst`    | `app/agents/analyst.py` | `logs/log_analyst.log`|
| `agent_visualizer` | `app/agents/visualizer.py` | `logs/log_visualizer.log` |
| `agent_sender`     | `app/agents/sender.py`  | `logs/log_sender.log` |

## Volumes

| Host path           | Purpose                    |
|---------------------|----------------------------|
| `storage/pdfs/`     | Generated PDFs and charts  |
| `storage/uploads/`  | Uploaded source files      |
| `logs/`             | Application & Traefik logs |
| `redis-data`        | Redis persistence (Docker volume) |

## Useful commands

```bash
# Container status
docker compose -f docker-compose.prod.yml ps

# API logs
docker logs -f reportagent_fastapi

# Celery worker logs
docker logs -f reportagent_celery_worker

# Traefik logs
docker logs -f reportagent_traefik

# Restart after .env changes
./deploy.sh
```

## Project structure

```
ReportAgent/
├── app/
│   ├── main.py
│   ├── tasks.py
│   ├── celery_app.py
│   ├── agents/
│   ├── models/
│   ├── utils/
│   ├── samples/
│   ├── Dockerfile
│   └── requirements.txt
├── samples/
├── traefik/
├── scripts/
├── storage/
├── logs/
├── .github/workflows/
│   ├── ci.yml
│   └── deploy-vps.yml
├── docker-compose.prod.yml
├── docker-compose.dev.yml
├── deploy.sh
├── deploy-dev.sh
└── .env.example
```

## Troubleshooting: Docker Hub timeout

Ошибка вида:

```text
failed to fetch anonymous token: read tcp ...->104.18.43.178:443: connection timed out
```

означает, что Docker не может скачать `traefik` / `redis` с Docker Hub (часто на WSL, VPN, корпоративной сети).

### Быстрое решение (локально)

```bash
./deploy-dev.sh
```

Traefik не нужен — приложение на `http://localhost:8000`.

### Зеркало Redis (production / dev)

В `.env`:

```bash
REDIS_IMAGE=public.ecr.aws/docker/library/redis:7-alpine
```

Затем снова `./deploy.sh` или `./deploy-dev.sh`.

### Повторные попытки pull

```bash
PULL_RETRIES=10 PULL_RETRY_DELAY=30 ./deploy.sh
```

### Если образы уже скачаны

```bash
SKIP_PULL=1 ./deploy.sh
```

### Docker registry mirror (WSL / Ubuntu)

`/etc/docker/daemon.json`:

```json
{
  "registry-mirrors": ["https://mirror.gcr.io"]
}
```

```bash
sudo systemctl restart docker   # Linux
# Docker Desktop: Settings → Docker Engine → вставить JSON → Apply
```

### VPS

На VPS с нормальным доступом к Docker Hub `./deploy.sh` обычно работает с первого раза. На ноутбуке тестируйте через `./deploy-dev.sh`.

## License

MIT
