# ReportAgent

Micro-SaaS for generating PDF reports with charts from CSV/Excel uploads or public Google Sheets. Reports are delivered by email via SMTP.

**v1.4** — Prometheus + Grafana observability, Telegram alerts, agent metrics.

**v1.3** — voice input (Whisper + GPT intent), API keys, per-user preferences, SQLite memory.

## Architecture

```
Client → Traefik / nginx (TLS) → FastAPI → Celery → Redis
                         ↓              ↓
                    Voice (Whisper   context_loader → parser → analyst → visualizer → sender
                     + GPT intent)         ↓
                                      SQLite (users.db)
```

| Service           | Role                                              |
|-------------------|---------------------------------------------------|
| **fastapi**       | HTTP API, auth middleware, preferences            |
| **celery_worker** | Background report pipeline                        |
| **redis**         | Celery broker & result backend                    |
| **SQLite**        | Users, API keys, preferences, request history     |
| **traefik**       | Reverse proxy, Let's Encrypt SSL (optional)       |
| **prometheus**    | Metrics collection & alert rules                  |
| **grafana**       | Dashboards (Traefik + basic auth)                 |
| **alertmanager**  | Telegram notifications on incidents               |
| **celery_beat**   | Periodic Celery queue metrics                     |

## Quick start (local development — WSL / laptop)

Без Traefik. API на **http://localhost:8000/docs**.

```bash
cp .env.example .env
# Опционально для локальных тестов без ключей:
# echo "DISABLE_AUTH=true" >> .env

chmod +x deploy-dev.sh scripts/healthcheck_celery.sh scripts/pull-images.sh
./deploy-dev.sh
```

Проверка:

```bash
curl http://localhost:8000/health

# Полный сценарий: ключ → preferences → отчёт
python3 -m pip install httpx   # один раз, если нет
python3 scripts/test_api_key.py
```

Если Docker Hub недоступен, в `.env` укажите зеркало Redis:

```bash
REDIS_IMAGE=public.ecr.aws/docker/library/redis:7-alpine
```

## Authentication & user memory

### Получить API-ключ (без аутентификации)

```bash
curl -X POST https://ваш-домен/api/keys/generate \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com"}'
```

Ответ:

```json
{
  "api_key": "…",
  "user_id": "uuid-…"
}
```

Сохраните `api_key` — он показывается **один раз** при создании.

### Использовать ключ

Все защищённые эндпоинты требуют заголовок:

```http
X-API-Key: ваш_ключ
```

Исключения (без ключа): `/health`, `/metrics`, `/docs`, `/openapi.json`, `/redoc`, `/`, `/api/keys/generate`.

### Локально без ключей

В `.env`:

```bash
DISABLE_AUTH=true
```

**Не используйте в production.**

### Предпочтения пользователя

```bash
# Получить
curl https://ваш-домен/api/preferences -H "X-API-Key: KEY"

# Обновить
curl -X PUT https://ваш-домен/api/preferences \
  -H "X-API-Key: KEY" \
  -H "Content-Type: application/json" \
  -d '{"theme": "dark", "preferred_chart_type": "pie", "default_email": "user@example.com"}'

# Сбросить к дефолтам
curl -X DELETE https://ваш-домен/api/preferences -H "X-API-Key: KEY"
```

| Поле                   | Значения              | Эффект                                      |
|------------------------|-----------------------|---------------------------------------------|
| `preferred_chart_type` | `bar`, `line`, `pie`  | Тип графиков в отчёте                       |
| `theme`                | `light`, `dark`       | Цветовая схема графиков                     |
| `default_email`        | email                 | Email по умолчанию, если не указан в запросе |
| `company_logo_url`     | URL                   | Логотип в PDF (если доступен по URL)        |
| `timezone`             | IANA, напр. `UTC`     | Метаданные (расширяемо)                     |

## Voice input

Голосовой запрос: аудио → Whisper (транскрипция) → GPT-4o-mini (intent) → отчёт или уточняющий вопрос.

### Требования

| Переменная | Описание |
|------------|----------|
| `OPENAI_API_KEY` | **Обязателен** для голоса (Whisper + LLM) |
| `OPENAI_BASE_URL` | Для [ProxyAPI.ru](https://proxyapi.ru): `https://api.proxyapi.ru/openai/v1`. Пусто = официальный OpenAI |
| `VOICE_ENABLED` | `true` / `false` — вкл/выкл эндпоинты |
| `WHISPER_MODEL` | `whisper-1` (OpenAI API) |
| `LLM_MODEL` | `gpt-4o-mini` (intent parsing) |
| `MAX_AUDIO_SIZE_MB` | Лимит размера файла (по умолчанию 25) |
| `ALLOWED_AUDIO_FORMATS` | `mp3,wav,m4a,ogg` |

В Docker-образе установлен **ffmpeg** (для pydub / конвертации). На хосте ffmpeg опционален.

Без `OPENAI_API_KEY` эндпоинты `/voice/*` возвращают **501 Not Implemented**.

### Поддерживаемые форматы

`mp3`, `wav`, `m4a`, `ogg` — до `MAX_AUDIO_SIZE_MB` МБ.

### `POST /voice/generate_report`

Требует `X-API-Key`. Form-data: поле `audio` (файл), опционально `email`.

```bash
curl -X POST https://ваш-домен/voice/generate_report \
  -H "X-API-Key: YOUR_KEY" \
  -F "audio=@recording.m4a" \
  -F "email=user@example.com"
```

**Ответ** `202`:

```json
{
  "task_id": "abc-123",
  "status": "queued",
  "transcript": "Создай отчёт по Google Sheets ...",
  "intent": { "source_type": "sheets_url", "chart_type": "pie", ... },
  "download_url": "/tasks/abc-123/pdf"
}
```

Если данных недостаточно — `status: "needs_clarification"` и поля `clarification_question`, `partial_intent`.  
`task_id` сохраняется в Redis для follow-up.

### `POST /voice/clarify`

```bash
curl -X POST https://ваш-домен/voice/clarify \
  -H "X-API-Key: YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"task_id": "voice-abc...", "answer": "используй колонку revenue из Google Sheets"}'
```

### Уточняющие вопросы

| Ситуация | Пример вопроса |
|----------|----------------|
| Не распознана речь | Повторите запрос чётче |
| Нет источника данных | Укажите ссылку на Google Sheets |
| Запрошен файл голосом | Предложите Sheets URL или `POST /generate_report` с файлом |

Статус уточнения: `GET /tasks/{task_id}` → `NEEDS_CLARIFICATION`.

### Тест

```bash
# 1. ReportAgent API key (НЕ OpenAI key!)
API_KEY=$(curl -s -X POST "https://ваш-домен/api/keys/generate" \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com"}' | jq -r .api_key)

# 2. Убедитесь, что файл существует (curl error 26 = файл не найден)
ls -la recording.m4a

curl -X POST "https://ваш-домен/voice/generate_report" \
  -H "X-API-Key: $API_KEY" \
  -F "audio=@recording.m4a"

# Скрипт (stdlib, без pip install):
python3 scripts/test_voice.py \
  --base-url https://ваш-домен \
  --api-key "$API_KEY" \
  --audio /path/to/recording.wav
```

| Ключ | Куда |
|------|------|
| ReportAgent API key | Заголовок `X-API-Key` (из `/api/keys/generate`) |
| OpenAI `sk-...` | Только в `.env` на сервере как `OPENAI_API_KEY` |

Логи: `logs/log_voice.log`. История запросов: `history.request_type = 'voice'`.

## Monitoring with Prometheus & Grafana

Полная видимость API, агентов, очереди Celery, голосовых запросов и ресурсов хоста.

### Быстрый старт

1. Добавьте в `.env` (см. `.env.example`):

```bash
GRAFANA_ADMIN_PASSWORD=your_secure_password
GRAFANA_DOMAIN=grafana.ваш-домен
PROMETHEUS_RETENTION_DAYS=15
TELEGRAM_BOT_TOKEN=123456:ABC...   # от @BotFather
TELEGRAM_CHAT_ID=-123456789        # ID чата/группы
ALERTS_ENABLED=true
```

2. Деплой:

```bash
./deploy.sh
```

3. Откройте:

| URL | Описание |
|-----|----------|
| `https://ваш-домен/metrics` | Prometheus exposition (без auth) |
| `https://grafana.ваш-домен/d/ReportAgent-Main/reportagent-main` | Главный дашборд |

Grafana защищена **дважды**: Traefik basic auth + логин Grafana (`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`).

При первом деплое без `GRAFANA_ADMIN_PASSWORD` в `.env` пароль генерируется автоматически и выводится в лог `deploy.sh`.

### Telegram-бот для алертов

1. Создайте бота через [@BotFather](https://t.me/BotFather) → `/newbot` → скопируйте токен в `TELEGRAM_BOT_TOKEN`.
2. Добавьте бота в группу или напишите ему `/start` в личку.
3. Узнайте `chat_id`:
   - личный чат: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   - группа: добавьте бота, отправьте сообщение, снова `getUpdates` — `chat.id` (отрицательное число).
4. `./deploy.sh` рендерит `alertmanager/alertmanager.yml` из шаблона.

Тест алертов:

```bash
python3 scripts/test_alerts.py --base-url https://ваш-домен --telegram
```

### Метрики вручную

```bash
curl -s https://ваш-домен/metrics | head -40
```

Ключевые метрики:

| Метрика | Назначение |
|---------|------------|
| `report_requests_total` | RPS по эндпоинтам |
| `agent_duration_seconds` | Время работы агентов |
| `agent_errors_total` | Ошибки агентов |
| `report_generation_duration_seconds` | Полный цикл отчёта |
| `celery_queue_length` | Длина очереди Celery |
| `voice_transcriptions_total` | Успех/фейл Whisper |
| `active_users` | Активные пользователи (30 дней) |
| `database_size_bytes` | Размер `users.db` |

### Правила алертов

Файл `prometheus/alerts.yml`:

- **HighErrorRate** — 5xx > 5% за 5 мин
- **CeleryQueueBacklog** — очередь > 20 задач
- **AgentLongRunning** — p95 агента > 30 с
- **HighVoiceFailureRate** — ошибки голоса > 20%
- **ContainerDown** — FastAPI metrics недоступны
- **HighCPUUsage** — CPU хоста > 85% (нужен `node_exporter`)
- **DatabaseGrowth** — `users.db` > 1 GB

### VPS с 1–2 GB RAM

Отключите сбор метрик хоста:

```bash
OBSERVABILITY_HOST_METRICS=false
```

Останутся Prometheus + Grafana + метрики приложения.

### Grafana setup script

```bash
./scripts/setup-grafana.sh
```

Проверяет provisioning и опционально создаёт API-ключ Grafana.

## Production (VPS)

### Режим Traefik (порты 80/443 на ReportAgent)

```bash
cp .env.example .env   # DOMAIN, SMTP, LETSENCRYPT_EMAIL
docker network create traefik_network || true
chmod +x deploy.sh
./deploy.sh
```

Проверка: `https://ваш-домен/health`

### Режим external nginx (порты 80/443 уже заняты, напр. SMDG)

В `.env` на VPS:

```bash
TRAEFIK_ENABLED=false
EXTERNAL_NGINX_NETWORK=smdg_default   # имя сети вашего nginx-контейнера
DOMAIN=reportagent.fileguardian.info  # поддомен ReportAgent
```

```bash
./deploy.sh
```

**Важно:**

- `curl http://localhost:8000/health` на VPS **не сработает** — порт 8000 не проброшен на хост, только внутри Docker.
- Проверяйте через поддомен: `https://ReportAgent.fileguardian.info/health`
- Корневой домен (`fileguardian.info`) может быть **другим сервисом** (SMDG) — это нормально.

Проверка изнутри Docker:

```bash
docker exec reportagent_fastapi curl -s http://localhost:8000/health
docker exec smdg-nginx-1 curl -s http://reportagent_fastapi:8000/health
```

Пример nginx: `docs/nginx-docker-existing.example.conf`

## GitHub Actions — автодеплой на VPS

Workflows в `.github/workflows/`:

| Workflow | Триггер | Назначение |
|----------|---------|------------|
| `ci.yml` | Pull Request → `main` / `master` | Тесты, `compileall`, `docker compose config`, сборка образа |
| `deploy-vps.yml` | Push → `main` / `master`, `workflow_dispatch` | CI + SSH-деплой на VPS |

### Однократная подготовка VPS

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER   # перелогиниться
docker network create traefik_network 2>/dev/null || true
```

SSH-ключ для GitHub Actions — в Secret `VPS_SSH_PRIVATE_KEY`.

### Secrets (Settings → Secrets and variables → Actions)

| Secret | Описание |
|--------|----------|
| `VPS_HOST` | IP или домен VPS |
| `VPS_USER` | SSH-пользователь |
| `VPS_SSH_PRIVATE_KEY` | Приватный SSH-ключ |
| `VPS_PORT` | SSH-порт (опционально, по умолчанию 22) |
| `GIT_DEPLOY_TOKEN` | GitHub PAT для приватного репо (`repo` scope) |

### Variables

| Variable | Пример | Описание |
|----------|--------|----------|
| `DEPLOY_PATH` | `~/ReportAgent` | Путь на VPS |
| `DOMAIN` | `reportagent.fileguardian.info` | Домен **в нижнем регистре** для optional health-check |
| `SKIP_EXTERNAL_HEALTH_CHECK` | `true` | Пропустить проверку `https://DOMAIN/health` |

### Первый автодеплой

```bash
cd ~/ReportAgent
cp .env.example .env && nano .env
mkdir -p app/data storage/pdfs storage/uploads logs traefik/acme
touch traefik/acme/acme.json && chmod 600 traefik/acme/acme.json
```

Запушьте в `master` — workflow задеплоит автоматически.

## Синхронизация: localhost ↔ GitHub ↔ VPS

**Источник правды для кода — GitHub (`master`).**  
Через git **не синхронизируются**: `.env`, `app/data/*.db`, `storage/`, `logs/`.

```
localhost (WSL)  ──push──►  GitHub  ──Actions/SSH──►  VPS
     ▲                        │
     └──────── pull ──────────┘
```

| Где правите | Действия |
|-------------|----------|
| **localhost (WSL)** | `git push origin master` → автодеплой |
| **VPS вручную** | `cd ~/ReportAgent && ./scripts/sync-pull.sh --deploy` |

### Что не коммитить

| Файл / папка | Примечание |
|--------------|------------|
| `.env` | Секреты, SMTP, DOMAIN |
| `app/data/*.db` | SQLite с API-ключами и историей |
| `storage/`, `logs/` | Runtime-данные |

## Деплой на VPS (вручную)

### 1. Настройка `.env`

| Переменная | Описание |
|------------|----------|
| `DOMAIN` | Домен ReportAgent (поддомен, если nginx shared) |
| `LETSENCRYPT_EMAIL` | Email для Let's Encrypt (Traefik mode) |
| `SMTP_*` | Настройки почты |
| `SECRET_KEY` | Случайная строка |
| `DATABASE_URL` | В Docker задаётся автоматически (`sqlite:////app/app/data/users.db`). В `.env` можно указать `sqlite:///./app/data/users.db` для ясности |
| `DEFAULT_PREFERRED_CHART_TYPE` | `bar` / `line` / `pie` для новых пользователей |
| `TRAEFIK_ENABLED` | `true` — Traefik; `false` — host/external nginx |
| `EXTERNAL_NGINX_NETWORK` | Имя Docker-сети nginx (режим B) |
| `OPENAI_API_KEY` | Для голосового ввода (Whisper + GPT) |
| `OPENAI_BASE_URL` | ProxyAPI: `https://api.proxyapi.ru/openai/v1` |
| `VOICE_ENABLED` | `true` — включить `/voice/*` |
| `GRAFANA_DOMAIN` | Поддомен Grafana, напр. `grafana.example.com` |
| `GRAFANA_ADMIN_PASSWORD` | Пароль admin Grafana + Traefik basic auth |
| `TELEGRAM_BOT_TOKEN` | Токен бота для Alertmanager |
| `TELEGRAM_CHAT_ID` | Chat ID для алертов |
| `ALERTS_ENABLED` | `true` / `false` |
| `OBSERVABILITY_HOST_METRICS` | `false` на слабом VPS (без node_exporter/cadvisor) |

### 2. Подготовка и запуск

```bash
docker network create traefik_network 2>/dev/null || true
mkdir -p app/data storage/pdfs storage/uploads logs traefik/acme
touch traefik/acme/acme.json && chmod 600 traefik/acme/acme.json
chmod +x deploy.sh scripts/healthcheck_celery.sh
./deploy.sh
```

### 3. Проверка

```bash
# External nginx mode — через поддомен
curl https://ReportAgent.fileguardian.info/health

# Traefik mode — через DOMAIN из .env
curl https://ваш-домен/health

# Swagger
# https://ваш-домен/docs
```

### 4. Тест отчёта с API-ключом

```bash
# 1. Ключ
API_KEY=$(curl -s -X POST "https://ваш-домен/api/keys/generate" \
  -H "Content-Type: application/json" \
  -d '{"email": "you@example.com"}' | jq -r .api_key)

# 2. Отчёт
TASK_ID=$(curl -s -X POST "https://ваш-домен/generate_report" \
  -H "X-API-Key: $API_KEY" \
  -F "file=@samples/sample_sales.csv" | jq -r .task_id)

# 3. PDF (~10 сек)
curl -OJ -H "X-API-Key: $API_KEY" "https://ваш-домен/tasks/${TASK_ID}/pdf"
```

## API

### Публичные эндпоинты (без `X-API-Key`)

| Method | Path | Описание |
|--------|------|----------|
| `GET` | `/health` | Healthcheck |
| `GET` | `/metrics` | Prometheus metrics (no auth) |
| `GET` | `/docs`, `/redoc`, `/openapi.json` | Swagger / OpenAPI |
| `POST` | `/api/keys/generate` | Создать API-ключ |

### Защищённые эндпоинты (требуют `X-API-Key`)

| Method | Path | Описание |
|--------|------|----------|
| `GET` | `/api/preferences` | Текущие настройки |
| `PUT` | `/api/preferences` | Обновить настройки |
| `DELETE` | `/api/preferences` | Сбросить к дефолтам |
| `POST` | `/generate_report` | Поставить задачу на отчёт |
| `POST` | `/voice/generate_report` | Отчёт из голосового сообщения (501 без OpenAI) |
| `POST` | `/voice/clarify` | Уточнение для голосового запроса |
| `GET` | `/tasks/{task_id}` | Статус задачи |
| `GET` | `/tasks/{task_id}/pdf` | Скачать PDF |
| `GET` | `/samples/sample_sales.csv` | Тестовый CSV |

### `POST /generate_report`

Multipart form:

| Field        | Type   | Required | Description                    |
|--------------|--------|----------|--------------------------------|
| `file`       | file   | no*      | CSV, `.xlsx`, `.xls`           |
| `sheets_url` | string | no*      | Public Google Sheets URL       |
| `email`      | string | no       | Email; если пусто — `default_email` из preferences |

\* Укажите **либо** `file`, **либо** `sheets_url`.

**Headers:** `X-API-Key: …` (если `DISABLE_AUTH` не включён)

**Response** `202`:

```json
{
  "task_id": "abc-123",
  "status": "queued",
  "message": "Report generation started. Download at GET /tasks/abc-123/pdf when ready.",
  "download_url": "/tasks/abc-123/pdf",
  "user_id": "uuid-…",
  "usage_count": 1
}
```

`usage_count` — число запросов пользователя в таблице `history`.

### `POST /api/keys/generate`

```json
{ "email": "user@example.com" }
```

`email` опционален.

## Agents

| Agent                 | File                         | Log file                    |
|-----------------------|------------------------------|-----------------------------|
| `voice_orchestrator`  | `app/voice/orchestrator.py`  | `logs/log_voice.log`        |
| `agent_context_loader`| `app/agents/context_loader.py` | `logs/log_context_loader.log` |
| `agent_parser`        | `app/agents/parser.py`       | `logs/log_parser.log`       |
| `agent_analyst`       | `app/agents/analyst.py`      | `logs/log_analyst.log`      |
| `agent_visualizer`    | `app/agents/visualizer.py`   | `logs/log_visualizer.log`   |
| `agent_sender`        | `app/agents/sender.py`       | `logs/log_sender.log`       |

Pipeline: `context_loader` → `parser` → `analyst` → `visualizer` → `sender`

## Database (SQLite)

| Таблица | Назначение |
|---------|------------|
| `users` | `id`, `api_key`, `email`, `last_used_at`, `is_active` |
| `preferences` | chart type, theme, default email, logo URL, timezone |
| `history` | Аналитика запросов (`user_id`, `task_id`, summary) |

- Файл: `app/data/users.db` (создаётся при старте)
- Миграции: `app/db/migrations/001_init.sql` (применяются автоматически)
- В Docker: volume `./app/data:/app/app/data`

API-ключи в логах маскируются (`****abcd` — только последние 4 символа).

## Volumes

| Host path           | Purpose                         |
|---------------------|---------------------------------|
| `app/data/`         | SQLite `users.db` (ключи, prefs)|
| `storage/pdfs/`     | Generated PDFs and charts       |
| `storage/uploads/`  | Uploaded source files           |
| `logs/`             | Application & Traefik logs      |
| `redis-data`        | Redis persistence (Docker vol.) |

## Useful commands

```bash
# Container status
docker compose -f docker-compose.prod.yml ps

# API logs
docker logs -f reportagent_fastapi

# Celery worker logs
docker logs -f reportagent_celery_worker

# Health inside container (VPS, external nginx mode)
docker exec reportagent_fastapi curl -s http://localhost:8000/health

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
│   │   ├── context_loader.py
│   │   ├── parser.py
│   │   ├── analyst.py
│   │   ├── visualizer.py
│   │   └── sender.py
│   ├── voice/
│   │   ├── transcriber.py
│   │   ├── intent_parser.py
│   │   ├── orchestrator.py
│   │   └── models.py
│   ├── routers/
│   │   ├── keys.py
│   │   ├── preferences.py
│   │   └── voice.py
│   ├── db/
│   │   ├── database.py
│   │   ├── init_db.py
│   │   └── migrations/
│   ├── middleware/
│   │   ├── auth.py
│   │   └── request_logging.py
│   ├── models/
│   ├── data/              # users.db (gitignored)
│   ├── utils/
│   ├── samples/
│   ├── Dockerfile
│   └── requirements.txt
├── scripts/
│   ├── test_api_key.py
│   ├── test_voice.py
│   ├── test_alerts.py
│   ├── setup-grafana.sh
│   ├── render-alertmanager.sh
│   └── github-deploy.sh
├── docs/
├── prometheus/
│   ├── prometheus.yml
│   └── alerts.yml
├── alertmanager/
│   └── alertmanager.yml.template
├── grafana/
│   ├── provisioning/
│   └── dashboards/
├── traefik/
├── storage/
├── logs/
├── .github/workflows/
├── docker-compose.prod.yml
├── docker-compose.dev.yml
├── deploy.sh
├── deploy-dev.sh
└── .env.example
```

## Troubleshooting

### `curl localhost:8000` — connection refused (VPS)

В режиме **external nginx** FastAPI не слушает хост-порт 8000. Используйте поддомен или:

```bash
docker exec reportagent_fastapi curl -s http://localhost:8000/health
```

### `reportagent_fastapi is unhealthy` после деплоя

Частая причина — в `.env` остался старый `DATABASE_URL=postgresql://…`.  
Docker Compose задаёт SQLite автоматически; обновите `.env`:

```bash
DATABASE_URL=sqlite:///./app/data/users.db
```

Логи:

```bash
docker logs reportagent_fastapi --tail 50
```

### Корневой домен отвечает другим сервисом

`https://fileguardian.info` → SMDG, `https://ReportAgent.fileguardian.info` → ReportAgent.  
Проверяйте health на **поддомене** ReportAgent.

### Whisper 401 / пустой transcript (ProxyAPI)

Ключ ProxyAPI **не работает** с `api.openai.com`. В `.env` на VPS:

```bash
OPENAI_API_KEY=ваш_ключ_из_proxyapi.ru
OPENAI_BASE_URL=https://api.proxyapi.ru/openai/v1
```

```bash
./deploy.sh
./scripts/diagnose_voice.sh recording.wav
```

### port 80 already allocated

См. варианты A/B/C ниже.

### Docker Hub timeout

Локально: `./deploy-dev.sh`.  
Production: `REDIS_IMAGE=public.ecr.aws/docker/library/redis:7-alpine` в `.env`.

---

## Troubleshooting: port 80 already allocated

```text
Bind for 0.0.0.0:80 failed: port is already allocated
```

### Вариант A — освободить 80/443 для Traefik

```bash
sudo systemctl stop nginx && sudo systemctl disable nginx
# или: docker stop <контейнер_на_80>
./deploy.sh
```

### Вариант B — nginx уже в Docker (`smdg-nginx-1`)

```bash
TRAEFIK_ENABLED=false
EXTERNAL_NGINX_NETWORK=smdg_default
DOMAIN=reportagent.fileguardian.info
```

Добавьте `server_name` для поддомена в nginx → `http://reportagent_fastapi:8000`.  
Пример: `docs/nginx-docker-existing.example.conf`

```bash
docker rm -f reportagent_traefik 2>/dev/null || true
./deploy.sh
docker exec smdg-nginx-1 curl -s http://reportagent_fastapi:8000/health
```

### Вариант C — nginx на хосте

`TRAEFIK_ENABLED=false`, FastAPI на `127.0.0.1:8000` — `docs/nginx-host.example.conf`.

## License

MIT
