# ReportAgent

Micro-SaaS for generating reports (PDF, Excel, PowerPoint, Notion, Google Slides) with charts from CSV/Excel uploads or public Google Sheets.

**v1.5** — multi-format output (Excel, PPTX, Notion, Google Slides), format preferences, voice format detection.

**v1.4** — Prometheus + Grafana observability, Telegram alerts, agent metrics.

**v1.3** — voice input (Whisper + GPT intent), API keys, per-user preferences, SQLite memory.

## Architecture

```
Client → Traefik / nginx (TLS) → FastAPI → Celery → Redis
                         ↓              ↓
                    Voice (Whisper   context_loader → parser → analyst → visualizer → formatter → sender (PDF)
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
  "id": "uuid-…",
  "key": "ra_abc123…",
  "key_prefix": "ra_abc12",
  "name": "Default",
  "user_id": "uuid-…"
}
```

Сохраните `key` — полный ключ показывается **один раз** при создании. Новые ключи имеют префикс `ra_`.

### API Key Management

Управление несколькими ключами на одного пользователя. Ключи хранятся в БД только как SHA-256 хеш; в списках отображается только `key_prefix` (первые 8 символов).

> **Важно:** полный ключ возвращается только при `POST /api/keys/generate` и `POST /api/keys/{id}/rotate`. Сохраните его сразу — повторно получить нельзя.

#### Список ключей

```bash
curl https://ваш-домен/api/keys \
  -H "X-API-Key: ваш_ключ"
```

```json
{
  "keys": [
    {
      "id": "uuid-1",
      "key_prefix": "ra_abc12",
      "name": "Production",
      "created_at": "2026-01-01T10:00:00",
      "last_used_at": "2026-01-15T09:00:00",
      "expires_at": null,
      "is_active": true,
      "is_current": true
    }
  ]
}
```

#### Создать дополнительный ключ (для существующего пользователя)

```bash
curl -X POST https://ваш-домен/api/keys/generate \
  -H "X-API-Key: ваш_ключ" \
  -H "Content-Type: application/json" \
  -d '{"name": "CI/CD", "expires_at": "2026-12-31T23:59:59Z"}'
```

`expires_at` опционален (`null` = бессрочный).

#### Отозвать ключ

```bash
curl -X DELETE https://ваш-домен/api/keys/{key_id} \
  -H "X-API-Key: ваш_ключ"
```

Нельзя отозвать последний активный ключ (ответ `400`). Отозванные ключи не удаляются — `is_active` становится `false`.

#### Ротация ключа

Сгенерировать новый ключ и деактивировать старый (удобно при компрометации):

```bash
curl -X POST https://ваш-домен/api/keys/{key_id}/rotate \
  -H "X-API-Key: ваш_ключ" \
  -H "Content-Type: application/json" \
  -d '{"new_name": "Production (rotated)"}'
```

```json
{
  "old_key_prefix": "ra_abc12",
  "new_key": "ra_def456…",
  "new_key_id": "uuid-2"
}
```

Сохраните `new_key` — он показывается один раз.

#### Переименовать ключ

```bash
curl -X PUT https://ваш-домен/api/keys/{key_id}/rename \
  -H "X-API-Key: ваш_ключ" \
  -H "Content-Type: application/json" \
  -d '{"name": "Staging"}'
```

#### Обратная совместимость

Старые ключи из поля `users.api_key` продолжают работать. При первом запуске после обновления они автоматически переносятся в таблицу `api_keys` (имя `Legacy`).

#### Тест

```bash
python scripts/test_api_keys.py --base-url http://localhost:8000
```

## Admin API

> **Только для администратора.** Не используйте `ADMIN_API_KEY` в клиентских приложениях. Все действия логируются в `logs/log_admin.log` и таблицу `audit_log`.

### Генерация ADMIN_API_KEY

При первом деплое `./deploy.sh` автоматически генерирует ключ, если в `.env` стоит placeholder:

```bash
ADMIN_API_KEY=change-me-generate-on-deploy
```

Или вручную:

```bash
openssl rand -hex 24
```

Добавьте значение в `.env` и перезапустите: `./deploy.sh`

### Аутентификация

Все эндпоинты `/admin/*` требуют заголовок:

```http
X-Admin-Key: ваш_admin_ключ
```

Альтернатива: `X-API-Key` с тем же значением `ADMIN_API_KEY` (для совместимости).

Опционально ограничьте IP в `.env`:

```bash
ADMIN_ALLOWED_IPS=203.0.113.10,198.51.100.5
```

### Проверка доступа

```bash
curl -s https://ваш-домен/admin/health/all \
  -H "X-Admin-Key: $ADMIN_API_KEY" | jq .
```

### Управление пользователями

```bash
# Список пользователей
curl "https://ваш-домен/admin/users?page=1&limit=50&search=user@" \
  -H "X-Admin-Key: $ADMIN_API_KEY"

# Детали пользователя
curl "https://ваш-домен/admin/users/{user_id}" \
  -H "X-Admin-Key: $ADMIN_API_KEY"

# Заблокировать (отзывает все ключи)
curl -X POST "https://ваш-домен/admin/users/{user_id}/block" \
  -H "X-Admin-Key: $ADMIN_API_KEY"

# Разблокировать (ключи не восстанавливаются)
curl -X POST "https://ваш-домен/admin/users/{user_id}/unblock" \
  -H "X-Admin-Key: $ADMIN_API_KEY"

# Удалить пользователя (каскадно: ключи, вебхуки, history)
curl -X DELETE "https://ваш-домен/admin/users/{user_id}" \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

### Системное здоровье

```bash
curl https://ваш-домен/admin/health/all -H "X-Admin-Key: $ADMIN_API_KEY"
curl https://ваш-домен/admin/health/system -H "X-Admin-Key: $ADMIN_API_KEY"
```

### Celery

```bash
curl https://ваш-домен/admin/celery/status -H "X-Admin-Key: $ADMIN_API_KEY"
curl -X POST https://ваш-домен/admin/celery/purge-queue -H "X-Admin-Key: $ADMIN_API_KEY"
curl -X POST https://ваш-домен/admin/celery/restart-worker -H "X-Admin-Key: $ADMIN_API_KEY"
```

### Self-healing

```bash
curl https://ваш-домен/admin/self-healing/stats -H "X-Admin-Key: $ADMIN_API_KEY"
curl -X POST "https://ваш-домен/admin/self-healing/seed-fixes?overwrite=true" \
  -H "X-Admin-Key: $ADMIN_API_KEY"
curl -X POST https://ваш-домен/admin/self-healing/rebuild-index \
  -H "X-Admin-Key: $ADMIN_API_KEY"
curl -X DELETE https://ваш-домен/admin/self-healing/fixes/{fix_id} \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

Legacy-пути с подчёркиванием (`/admin/self_healing/...`) также поддерживаются.

### Логи

```bash
curl "https://ваш-домен/admin/logs?level=ERROR&hours=24&limit=100" \
  -H "X-Admin-Key: $ADMIN_API_KEY"

curl "https://ваш-домен/admin/logs/download?level=ERROR" \
  -H "X-Admin-Key: $ADMIN_API_KEY" -o logs.zip

curl -N "https://ваш-домен/admin/logs/stream?level=ERROR" \
  -H "X-Admin-Key: $ADMIN_API_KEY"
```

### Метрики

```bash
curl https://ваш-домен/admin/metrics/summary -H "X-Admin-Key: $ADMIN_API_KEY"
curl https://ваш-домен/admin/metrics/prometheus -H "X-Admin-Key: $ADMIN_API_KEY"
curl https://ваш-домен/admin/metrics/grafana-dashboard -H "X-Admin-Key: $ADMIN_API_KEY"
```

### Rate limiting

Пользовательские эндпоинты ограничены **100 запросов/минуту** по умолчанию (`RATE_LIMIT_REQUESTS_PER_MINUTE`).

```bash
curl https://ваш-домен/admin/rate-limits -H "X-Admin-Key: $ADMIN_API_KEY"

curl -X PUT https://ваш-домен/admin/rate-limits/global \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"limit": 200}'

curl -X PUT https://ваш-домен/admin/rate-limits/user/{user_id} \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"limit": 1000}'
```

### Тест

```bash
ADMIN_API_KEY=your_key python scripts/test_admin_api.py --base-url http://localhost:8000
```

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
| `default_output_format`| `pdf`, `excel`, `pptx`, `notion`, `google_slides` | Формат отчёта по умолчанию |

## Preview before sending

Перед генерацией полного отчёта пользователь может просмотреть **превью**: таблица (первые 50 строк), базовая статистика и графики. Данные хранятся в Redis **1 час** и **не** попадают в `history` до подтверждения.

### Поток

1. `POST /api/reports/preview` — загрузка файла или Google Sheets URL  
2. Ответ: `preview_id`, `data` (headers, rows, summary, charts), `expires_at`  
3. Графики: `GET /api/preview/chart/{preview_id}/{chart_index}` (PNG)  
4. Смена типа графика: `POST /api/reports/preview/regenerate-chart`  
5. Подтверждение: `POST /api/reports/preview/confirm` → полная генерация + email (опционально)

Файлы **> 10 MB** обрабатываются асинхронно (Celery). Опрашивайте `GET /api/reports/preview/status/{job_id}`.

### curl

```bash
curl -X POST https://ваш-домен/api/reports/preview \
  -H "X-API-Key: $API_KEY" \
  -F "file=@sample_sales.csv"

curl -X POST https://ваш-домен/api/reports/preview/confirm \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"preview_id":"uuid","output_format":"pdf"}'
```

На **Дашборде** — блок «Новый отчёт» с модальным превью.

```bash
python scripts/test_preview.py --base-url http://localhost:8000
```

## Output formats (Step 4)

Поддерживаемые форматы: `pdf`, `excel`, `pptx`, `notion`, `google_slides` (настраивается через `ALLOWED_OUTPUT_FORMATS`).

### Переменные окружения

| Переменная | Описание |
|------------|----------|
| `DEFAULT_OUTPUT_FORMAT` | Формат по умолчанию (`pdf`) |
| `ALLOWED_OUTPUT_FORMATS` | Список через запятую |
| `NOTION_INTEGRATION_TOKEN` | Internal Integration Token Notion |
| `NOTION_DATABASE_ID` | ID базы для сохранения отчётов |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Путь к JSON ключу сервисного аккаунта |
| `GOOGLE_SLIDES_TEMPLATE_ID` | ID шаблона презентации Google Slides |

### Установить формат по умолчанию

```bash
curl -X POST https://ваш-домен/api/preferences/output_format \
  -H "X-API-Key: KEY" \
  -H "Content-Type: application/json" \
  -d '{"default_output_format": "excel"}'
```

### Примеры curl

**PDF (по умолчанию, обратная совместимость):**

```bash
curl -X POST https://ваш-домен/generate_report \
  -H "X-API-Key: KEY" \
  -F "file=@sample_sales.csv"
# → download_url: /tasks/{id}/pdf
```

**Excel:**

```bash
curl -X POST https://ваш-домен/generate_report \
  -H "X-API-Key: KEY" \
  -F "file=@sample_sales.csv" \
  -F "output_format=excel"
# → download_url: /tasks/{id}/export
```

**PowerPoint:**

```bash
curl -X POST https://ваш-домен/generate_report \
  -H "X-API-Key: KEY" \
  -F "file=@sample_sales.csv" \
  -F "output_format=pptx"
```

**Notion** (требует `NOTION_INTEGRATION_TOKEN` + `NOTION_DATABASE_ID`):

```bash
curl -X POST https://ваш-домен/generate_report \
  -H "X-API-Key: KEY" \
  -F "sheets_url=https://docs.google.com/spreadsheets/d/..." \
  -F "output_format=notion"
# → GET /tasks/{id}/export редиректит на страницу Notion
```

**Google Slides** (требует `secrets/google-sa.json` + `GOOGLE_SLIDES_TEMPLATE_ID`):

```bash
curl -X POST https://ваш-домен/generate_report \
  -H "X-API-Key: KEY" \
  -F "file=@sample_sales.csv" \
  -F "output_format=google_slides"
```

### Скачивание результата

| Формат | Эндпоинт |
|--------|----------|
| PDF | `GET /tasks/{task_id}/pdf` (legacy, работает как раньше) |
| excel, pptx | `GET /tasks/{task_id}/export` |
| notion, google_slides | `GET /tasks/{task_id}/export` → redirect 302 |

### Настройка Notion

1. Создайте интеграцию: https://www.notion.so/my-integrations
2. Скопируйте **Internal Integration Token** → `NOTION_INTEGRATION_TOKEN`
3. Создайте базу данных в Notion, подключите интеграцию (Share → Invite)
4. Получите `database_id` из URL или через скрипт:

```bash
NOTION_INTEGRATION_TOKEN=secret_... python3 scripts/setup_notion.py
```

### Настройка Google Slides

1. Google Cloud Console → создайте проект, включите **Google Slides API** и **Google Drive API**
2. Создайте сервисный аккаунт → Keys → JSON → сохраните как `secrets/google-sa.json` (**не коммитьте**)
3. Создайте презентацию-шаблон с плейсхолдерами `%DATE%`, `%METRICS%`, `%CHART_1%`
4. Поделитесь шаблоном с email сервисного аккаунта (Editor)
5. Скопируйте ID из URL → `GOOGLE_SLIDES_TEMPLATE_ID`

```bash
GOOGLE_SERVICE_ACCOUNT_JSON=./secrets/google-sa.json python3 scripts/setup_google_slides.py
```

### Голосом

Intent parser распознаёт формат из речи:

- «сделай в Excel» → `excel`
- «отправь в Notion» → `notion`
- «создай презентацию» → `pptx`

### Тест всех форматов

```bash
python3 scripts/test_formats.py
```

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
  -d '{"email":"you@example.com"}' | jq -r .key)

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

## Self-healing RAG (Step 5)

Агенты автоматически учатся на ошибках: при падении ищут похожие случаи в ChromaDB, применяют известное исправление и сохраняют статистику.

### Как это работает

1. Агент падает → декоратор `@with_self_healing` извлекает сигнатуру ошибки.
2. ChromaDB ищет похожие записи (локальные эмбеддинги `all-MiniLM-L6-v2`, без OpenAI).
3. Если найдено решение с `was_successful=true` и `success_count > fail_count` → `FixExecutor` применяет технический фикс и повторяет вызов.
4. Успех → `success_count++`, алерт в Telegram. Неудача → новая запись для ручного разбора + алерт.
5. Раз в час Celery Beat (`learn_from_failures`) анализирует старые неудачи через GPT-4o-mini и создаёт кандидаты решений.

### Быстрый старт

```bash
# .env (см. .env.example)
SELF_HEALING_ENABLED=true
CHROMA_PERSIST_DIR=./chroma_data
ADMIN_API_KEY=...   # генерируется deploy.sh при первом деплое
```

```bash
./deploy.sh   # создаёт chroma_data/, монтирует volume
```

При первом запуске загружаются **seed-фиксы** из `app/self_healing/seed_fixes.json` (10 типовых ошибок).

### Ручное добавление фикса через API

```bash
ADMIN_KEY="ваш-admin-api-key"

# Добавить кандидат-решение
curl -X POST "https://ваш-домен/admin/self_healing/fixes" \
  -H "X-Admin-Key: $ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "error_text": "KeyError revenue column not found",
    "agent_name": "analyst",
    "solution_prompt": "Fuzzy match revenue to nearest column",
    "solution_code": "{\"action\": \"fuzzy_column_match\", \"params\": {\"_missing_column\": \"revenue\"}}"
  }'

# Подтвердить после проверки
curl -X POST "https://ваш-домен/admin/self_healing/confirm/{fix_id}" \
  -H "X-Admin-Key: $ADMIN_KEY"

# Статистика
curl "https://ваш-домен/admin/self_healing/stats" -H "X-Admin-Key: $ADMIN_KEY"
```

### Примеры seed-фиксов

| Ошибка | Решение |
|--------|---------|
| `pandas.errors.ParserError: tokenizing` | `sep=';'`, `engine='python'` |
| `KeyError: 'sales'` | fuzzy matching столбца |
| `matplotlib: no display` | `matplotlib.use('Agg')` |
| `openai.RateLimitError` | exponential backoff retry |
| `UnicodeDecodeError` CSV | `encoding='latin-1'` |

### Тестирование

```bash
python3 scripts/test_self_healing.py
python3 scripts/test_self_healing.py --base-url https://ваш-домен --admin-key "$ADMIN_API_KEY"
```

### Метрики и алерты

| Метрика | Назначение |
|---------|------------|
| `self_healing_attempts_total{agent_name,success}` | Попытки self-healing |
| `self_healing_duration_seconds` | Время попытки |
| `knowledge_base_size` | Записей в ChromaDB |
| `self_healing_fixes_applied_total{source}` | auto / manual |

Правило **SelfHealingLowSuccessRate** — success rate < 50% за час.

### Безопасность

- `solution_code` — только JSON action specs, **eval запрещён**
- Авто-фиксы кода только для `parser`, `analyst`, `visualizer`, `intent_parser`, `formatter`
- SMTP/отправка email — только prompt + алерт, без авто-патча
- Self-healing отключается при RAM < 1 GB или падении ChromaDB

### VPS с малым RAM

```bash
SELF_HEALING_ENABLED=false   # или OBSERVABILITY_HOST_METRICS=false + достаточно RAM
```

Логи: `logs/log_self_healing.json`. Периодическое обучение: **Celery Beat** (`celery_beat` контейнер), задача `learn_from_failures` каждый час.

## Webhooks — уведомления о готовности отчёта

Мгновенные POST-уведомления на ваш URL при завершении или ошибке генерации отчёта — без polling.

### События

| Событие | Когда |
|---------|-------|
| `report.completed` | Отчёт успешно сгенерирован |
| `report.failed` | Ошибка в pipeline (parser, analyst, formatter…) |

### Быстрый старт

```bash
# .env
WEBHOOK_ENABLED=true
WEBHOOK_PUBLIC_BASE_URL=https://reportagent.example.com
```

```bash
curl -X POST "https://ваш-домен/api/webhooks/register" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://myapp.com/report-callback",
    "events": ["report.completed", "report.failed"],
    "secret": "my-hmac-secret"
  }'
```

### Формат payload

```json
{
  "event": "report.completed",
  "task_id": "uuid",
  "status": "SUCCESS",
  "download_url": "https://reportagent.example.com/tasks/uuid/export",
  "output_format": "pdf",
  "timestamp": "2026-01-15T10:30:00Z",
  "user_id": "a1b2c3d4",
  "metadata": {
    "source_type": "file",
    "duration_seconds": 12.5,
    "retry_count": 0
  }
}
```

### API эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| `POST` | `/api/webhooks/register` | Зарегистрировать URL |
| `GET` | `/api/webhooks` | Список вебхуков |
| `GET` | `/api/dashboard/stats` | Статистика дашборда (30 дней) |
| `GET` | `/api/reports` | История отчётов (пагинация) |
| `DELETE` | `/api/reports/{task_id}` | Удалить отчёт и файлы |
| `PUT` | `/api/webhooks/{id}` | Обновить url / events |
| `POST` | `/api/webhooks/{id}/reactivate` | Включить после deactivate |
| `DELETE` | `/api/webhooks/{id}` | Удалить |
| `GET` | `/admin/webhooks/stats` | Статистика (X-Admin-Key) |

### Проверка подписи HMAC

Заголовок `X-Webhook-Signature` = HMAC-SHA256(secret, canonical JSON).

```python
import hashlib, hmac, json

def verify(secret, body, signature):
    payload = json.dumps(body, separators=(",", ":"), sort_keys=True)
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

### Локальное тестирование

```bash
python3 scripts/mock_webhook_server.py --port 9999 --secret my-secret
python3 scripts/test_webhook.py --base-url https://ваш-домен --api-key "$API_KEY"
```

Логи: `logs/log_webhook.log`. Метрики: `webhook_attempts_total`, `webhook_duration_seconds`.

## Payments (Stripe — primary)

Интеграция подписок через [Stripe Checkout](https://stripe.com/docs/checkout). ЮKassa остаётся опциональной альтернативой для РФ (см. ниже).

### Переменные окружения

```bash
STRIPE_SECRET_KEY=sk_test_...
STRIPE_PUBLISHABLE_KEY=pk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_ID_MONTHLY=price_xxx
STRIPE_PRICE_ID_YEARLY=price_yyy
STRIPE_PRICE_ID_PAYG=price_zzz
STRIPE_SUCCESS_URL=https://ваш-домен/success
STRIPE_CANCEL_URL=https://ваш-домен/cancel

FREEMIUM_REPORTS_LIMIT=5
PREMIUM_REPORTS_LIMIT=100
ENTERPRISE_REPORTS_LIMIT=1000
```

### Настройка Stripe Dashboard

1. Создайте продукты и **Prices** (monthly / yearly / one-time PAYG).
2. Скопируйте `price_...` в `STRIPE_PRICE_ID_*`.
3. **Developers → Webhooks → Add endpoint**:
   - URL: `https://ваш-домен/webhooks/stripe`
   - События: `checkout.session.completed`, `customer.subscription.*`, `invoice.payment_succeeded`, `invoice.payment_failed`
4. Скопируйте signing secret в `STRIPE_WEBHOOK_SECRET`.

Эндпоинт `/webhooks/stripe` **без аутентификации**; при невалидной подписи возвращает **401**.

### Тестовые карты (test mode)

| Карта | Результат |
|-------|-----------|
| `4242 4242 4242 4242` | Успешная оплата |
| `4000 0000 0000 0002` | Отклонена |

Локально: `stripe listen --forward-to localhost:8000/webhooks/stripe`

### API эндпоинты (Stripe)

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `GET` | `/api/payments/prices` | нет | Каталог тарифов |
| `POST` | `/api/payments/create-checkout` | `X-API-Key` | Checkout Session → `url` |
| `GET` | `/api/payments/subscription` | `X-API-Key` | Текущая подписка |
| `POST` | `/api/payments/cancel-subscription` | `X-API-Key` | Отмена в Stripe |
| `POST` | `/webhooks/stripe` | нет | Webhook Stripe |
| `GET` | `/admin/payments/subscriptions` | Admin | Список подписок |
| `GET` | `/admin/payments/revenue` | Admin | Доход за период |
| `POST` | `/admin/payments/refund/{payment_id}` | Admin | Возврат |

Пример checkout:

```bash
curl -X POST "https://ваш-домен/api/payments/create-checkout" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"price_id":"price_xxx"}'
```

Фронтенд: `/app#/pricing` (Stripe), `/app#/subscription`, `/app#/success`, `/app#/cancel`.

### Миграция БД (Stripe)

Файл: `app/db/migrations/008_add_stripe_integration.sql` — колонки `stripe_customer_id`, `stripe_subscription_id`, `provider`, `preferences.last_plan_notification_shown`.

Таблицы `subscriptions` и `payments` созданы в `007_add_yookassa_tables.sql`.

### Тестовый скрипт

```bash
pip install stripe
STRIPE_SECRET_KEY=sk_test_... STRIPE_PRICE_ID_MONTHLY=price_xxx python3 scripts/test_payments.py
```

### Метрики

- `payments_completed_total{provider="stripe"}`
- `payments_failed_total{provider="stripe"}`
- `active_subscriptions_total`
- `monthly_recurring_revenue` (USD cents, последние 30 дней)

---

## ЮKassa Payments (optional, RU)

Интеграция приёма оплаты подписок через [ЮKassa API v3](https://yookassa.ru/developers/using-api/interaction-format).

### Переменные окружения

```bash
YOOKASSA_SHOP_ID=ваш_shop_id
YOOKASSA_SECRET_KEY=ваш_секретный_ключ
YOOKASSA_API_URL=https://api.yookassa.ru/v3
YOOKASSA_RETURN_URL_SUCCESS=https://ваш-домен/payment/success
YOOKASSA_RETURN_URL_CANCEL=https://ваш-домен/payment/cancel

FREEMIUM_REPORTS_LIMIT=5
PREMIUM_REPORTS_LIMIT=100
ENTERPRISE_REPORTS_LIMIT=1000
PRICE_PREMIUM_MONTHLY=1990      # 19.90 ₽ (копейки)
PRICE_PREMIUM_YEARLY=19900      # 199.00 ₽
PRICE_ENTERPRISE=9990           # 99.90 ₽
```

### Создание магазина (тестовый режим)

1. Зарегистрируйтесь в [личном кабинете ЮKassa](https://yookassa.ru/).
2. Создайте **тестовый магазин** (shopId + secret key выпускаются автоматически).
3. Добавьте `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY` в `.env`.
4. Для тестовых карт используйте:
   - Mastercard: `5555 5555 5555 4444`
   - Visa: `4111 1111 1111 1111`

### HTTP-уведомления (webhooks)

В кабинете: **Интеграция → HTTP-уведомления**

| Параметр | Значение |
|----------|----------|
| URL | `https://ваш-домен/webhooks/yookassa` |
| События | `payment.succeeded`, `payment.waiting_for_capture`, `payment.canceled` |

Требования:
- URL только по **HTTPS** (порт 443/8443)
- Эндпоинт **без аутентификации** (исключён в `APIKeyAuthMiddleware`)
- Проверка подписи: заголовок `Content-Signature: sha256=<hmac>` (HMAC-SHA256 от raw body + `YOOKASSA_SECRET_KEY`)
- При невалидной подписи API возвращает **401**

### Тарифы

| План | Цена | Лимит отчётов / месяц |
|------|------|------------------------|
| Freemium | бесплатно | 5 |
| Premium Monthly | 19.90 ₽ | 100 |
| Premium Yearly | 199.00 ₽ | 100 (в месяц) |
| Enterprise | 99.90 ₽ | 1000 + Notion/Google Slides |

### API эндпоинты

| Метод | Путь | Auth | Описание |
|-------|------|------|----------|
| `POST` | `/api/payments/yookassa/create` | `X-API-Key` | Создать платёж, вернуть `confirmation_url` |
| `GET` | `/api/payments/yookassa/status/{payment_id}` | `X-API-Key` | Синхронизировать статус с ЮKassa |
| `POST` | `/webhooks/yookassa` | нет | Входящие уведомления ЮKassa |
| `GET` | `/admin/payments/yookassa` | `X-Admin-Key` | Список платежей |
| `GET` | `/admin/payments/yookassa/{payment_id}` | `X-Admin-Key` | Детали платежа |
| `POST` | `/admin/payments/yookassa/refund/{payment_id}` | `X-Admin-Key` | Возврат через `POST /v3/refunds` |

Пример создания платежа:

```bash
curl -X POST "https://ваш-домен/api/payments/yookassa/create" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"plan_type":"premium_monthly"}'
```

Ответ:

```json
{
  "payment_id": "22d6d597-000f-5000-9000-145f6df21d6f",
  "confirmation_url": "https://yoomoney.ru/checkout/payments/..."
}
```

Фронтенд: `/app#/pricing` → редирект на `confirmation_url` → возврат на `/payment/success`.

### Миграция БД

Файл: `app/db/migrations/007_add_yookassa_tables.sql`

Создаёт таблицы:
- `subscriptions` (лимиты, `yookassa_payment_id`, `yookassa_payment_method`)
- `payments` (история платежей, amount в **копейках**)

> Если в вашей БД уже применена миграция `007_add_admin_audit_log.sql`, переименуйте файл ЮKassa в `008_add_yookassa_tables.sql` перед деплоем.

### Метрики Prometheus

| Метрика | Описание |
|---------|----------|
| `yookassa_payments_total{status}` | События платежей |
| `yookassa_payments_amount_total` | Сумма успешных платежей (RUB) |
| `active_subscriptions_total` | Активные платные подписки |

### Тест

```bash
python3 scripts/test_yookassa.py \
  --base-url http://localhost:8000 \
  --api-key "$API_KEY" \
  --plan-type premium_monthly
```

Логи: `logs/log_payment_yookassa.log`.

## Frontend API (Dashboard & Reports)

Эндпоинты для UI: статистика, список отчётов, удаление. Требуют `X-API-Key`.

### `GET /api/dashboard/stats`

```bash
curl -s "https://ваш-домен/api/dashboard/stats" -H "X-API-Key: $API_KEY" | jq
```

```json
{
  "total_reports_last_30_days": 42,
  "success_rate": 95.2,
  "most_used_output_format": "pdf",
  "average_generation_time_seconds": 3.4,
  "active_webhooks_count": 2
}
```

### `GET /api/reports?page=1&limit=20`

```bash
curl -s "https://ваш-домен/api/reports?page=1&limit=20" -H "X-API-Key: $API_KEY" | jq
```

```json
{
  "reports": [
    {
      "task_id": "abc-123",
      "created_at": "2026-01-15 10:00:00",
      "status": "SUCCESS",
      "output_format": "pdf",
      "download_url": "/tasks/abc-123/pdf",
      "request_summary": "POST /generate_report format=pdf"
    }
  ],
  "total": 120,
  "page": 1,
  "limit": 20
}
```

Статус и `duration_seconds` обновляются в `history` при завершении Celery-задачи (`SUCCESS` / `FAILURE` / `PENDING`).

### `DELETE /api/reports/{task_id}`

```bash
curl -X DELETE "https://ваш-домен/api/reports/abc-123" -H "X-API-Key: $API_KEY"
# {"status":"deleted"}
```

Удаляет запись из `history` и каталоги `storage/pdfs/{task_id}/`, `storage/formatted/{task_id}/` (только свои отчёты).

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
| `self_healing_attempts_total` | Попытки self-healing |
| `knowledge_base_size` | Записей в базе знаний ChromaDB |
| `webhook_attempts_total` | Доставка webhooks |
| `webhook_duration_seconds` | Latency webhooks |

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

### External nginx (без Traefik) — Grafana

Если `TRAEFIK_ENABLED=false` и ReportAgent за **smdg-nginx**:

1. В `.env`:
   ```bash
   GRAFANA_DOMAIN=grafana.reportagent.fileguardian.info
   EXTERNAL_NGINX_NETWORK=smdg_frontend   # сеть вашего nginx
   ```
2. DNS: **A-запись** `grafana.reportagent.fileguardian.info` → IP VPS.
3. `./deploy.sh` — Grafana подключается к сети nginx (`docker-compose.prod.external-nginx.yml`).
4. В nginx добавьте proxy → `http://reportagent_grafana:3000` — пример: `docs/nginx-grafana.example.conf`.
5. Диагностика на VPS:
   ```bash
   ./scripts/diagnose_observability.sh
   ```

**Prometheus** внутри Docker использует **имена контейнеров** (`reportagent_fastapi:8000`), не `fastapi:8000`:

```bash
docker exec reportagent_prometheus wget -qO- http://reportagent_fastapi:8000/metrics | head -5
```

Без DNS для Grafana — SSH-туннель с VPS:

```bash
# на VPS
docker exec reportagent_grafana curl -s http://localhost:3000/api/health
```

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
| `POST` | `/api/keys/generate` | Создать API-ключ (онбординг или доп. ключ) |
| `GET` | `/api/keys` | Список ключей (маскированные) |
| `DELETE` | `/api/keys/{key_id}` | Отозвать ключ |
| `POST` | `/api/keys/{key_id}/rotate` | Ротировать ключ |
| `PUT` | `/api/keys/{key_id}/rename` | Переименовать ключ |

### Защищённые эндпоинты (требуют `X-API-Key`)

| Method | Path | Описание |
|--------|------|----------|
| `GET` | `/api/preferences` | Текущие настройки |
| `PUT` | `/api/preferences` | Обновить настройки |
| `DELETE` | `/api/preferences` | Сбросить к дефолтам |
| `POST` | `/api/preferences/output_format` | Установить `default_output_format` |
| `POST` | `/generate_report` | Поставить задачу на отчёт |
| `POST` | `/voice/generate_report` | Отчёт из голосового сообщения (501 без OpenAI) |
| `POST` | `/voice/clarify` | Уточнение для голосового запроса |
| `GET` | `/tasks/{task_id}` | Статус задачи |
| `GET` | `/tasks/{task_id}/pdf` | Скачать PDF (legacy) |
| `GET` | `/tasks/{task_id}/export` | Скачать excel/pptx или redirect Notion/Slides |
| `GET` | `/samples/sample_sales.csv` | Тестовый CSV |

### `POST /generate_report`

Multipart form:

| Field        | Type   | Required | Description                    |
|--------------|--------|----------|--------------------------------|
| `file`          | file   | no*      | CSV, `.xlsx`, `.xls`           |
| `sheets_url`    | string | no*      | Public Google Sheets URL       |
| `email`         | string | no       | Email; если пусто — `default_email` из preferences |
| `output_format` | string | no       | `pdf`, `excel`, `pptx`, `notion`, `google_slides` |

\* Укажите **либо** `file`, **либо** `sheets_url`. Если `output_format` не указан — используется `preferences.default_output_format` или `pdf`.

**Headers:** `X-API-Key: …` (если `DISABLE_AUTH` не включён)

**Response** `202`:

```json
{
  "task_id": "abc-123",
  "status": "queued",
  "message": "Report generation started (excel). Download at GET /tasks/abc-123/export when ready.",
  "download_url": "/tasks/abc-123/export",
  "output_format": "excel",
  "user_id": "uuid-…",
  "usage_count": 1
}
```

`usage_count` — число запросов пользователя в таблице `history`.

### `POST /api/keys/generate`

```json
{ "email": "user@example.com", "name": "My Key", "expires_at": "2026-12-31T23:59:59Z" }
```

`email` — только при первом онбординге (без `X-API-Key`). `name` и `expires_at` опциональны.

См. также [API Key Management](#api-key-management) выше.

## Agents

| Agent                 | File                         | Log file                    |
|-----------------------|------------------------------|-----------------------------|
| `voice_orchestrator`  | `app/voice/orchestrator.py`  | `logs/log_voice.log`        |
| `agent_context_loader`| `app/agents/context_loader.py` | `logs/log_context_loader.log` |
| `agent_parser`        | `app/agents/parser.py`       | `logs/log_parser.log`       |
| `agent_analyst`       | `app/agents/analyst.py`      | `logs/log_analyst.log`      |
| `agent_visualizer`    | `app/agents/visualizer.py`   | `logs/log_visualizer.log`   |
| `agent_formatter`     | `app/agents/formatter.py`    | `logs/log_formatter.log`    |
| `agent_sender`        | `app/agents/sender.py`       | `logs/log_sender.log`       |

Pipeline: `context_loader` → `parser` → `analyst` → `visualizer` → `formatter` (PDF delegates to `sender`)

## Database (SQLite)

| Таблица | Назначение |
|---------|------------|
| `users` | `id`, `api_key` (deprecated), `email`, `last_used_at`, `is_active` |
| `api_keys` | Несколько ключей на пользователя: `key_hash`, `key_prefix`, `name`, `expires_at`, `is_active` |
| `preferences` | chart type, theme, default email, logo URL, timezone, **default_output_format** |
| `history` | Аналитика запросов (`user_id`, `task_id`, summary) |
| `audit_log` | Журнал админ-действий (`action`, `target`, `admin_ip`) |
| `rate_limits` | Лимиты запросов (`__global__` и per-user) |

- Файл: `app/data/users.db` (создаётся при старте)
- Миграции: `app/db/migrations/*.sql` (применяются автоматически, последняя: `007_add_admin_audit_log.sql`)
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
│   │   ├── admin.py
│   │   ├── admin_self_healing.py
│   │   ├── admin_webhooks.py
│   │   ├── api_keys.py
│   │   ├── preferences.py
│   │   └── voice.py
│   ├── admin/
│   │   ├── auth.py
│   │   ├── dependency.py
│   │   ├── rate_limiter.py
│   │   ├── log_reader.py
│   │   └── system_health.py
│   ├── db/
│   │   ├── database.py
│   │   ├── admin_queries.py
│   │   ├── init_db.py
│   │   └── migrations/
│   ├── middleware/
│   │   ├── auth.py
│   │   ├── rate_limit.py
│   │   └── request_logging.py
│   ├── models/
│   ├── data/              # users.db (gitignored)
│   ├── utils/
│   ├── samples/
│   ├── Dockerfile
│   └── requirements.txt
├── scripts/
│   ├── test_api_key.py
│   ├── test_api_keys.py
│   ├── test_admin_api.py
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
