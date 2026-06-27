# Переменные окружения

Полный справочник из `.env.example`.

## Приложение

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `SECRET_KEY` | — | Общий секрет приложения |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `MAX_FILE_SIZE_MB` | `25` | Лимит загрузки файла |

## Auth / JWT

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `JWT_SECRET_KEY` | — | **Обязательно** (`openssl rand -hex 32`) |
| `JWT_ALGORITHM` | `HS256` | |
| `JWT_EXPIRE_MINUTES` | `15` | Срок JWT |
| `EMAIL_FROM` | — | Отправитель писем |
| `FRONTEND_URL` | — | `https://домен/app` |
| `DISABLE_AUTH` | — | `true` только для dev |

## Redis / Celery

| Переменная | По умолчанию |
|------------|--------------|
| `REDIS_URL` | `redis://redis:6379/0` |
| `CELERY_RESULT_EXPIRES` | `86400` |
| `REDIS_IMAGE` | `redis:7-alpine` |

## База данных

| Переменная | По умолчанию |
|------------|--------------|
| `DATABASE_URL` | `sqlite:///./app/data/users.db` |
| `DEFAULT_PREFERRED_CHART_TYPE` | `bar` |

## OpenAI / голос

| Переменная | Описание |
|------------|----------|
| `OPENAI_API_KEY` | Whisper + GPT |
| `OPENAI_BASE_URL` | ProxyAPI для РФ |
| `VOICE_ENABLED` | `true` / `false` |
| `WHISPER_MODEL` | `whisper-1` |
| `LLM_MODEL` | `gpt-4o-mini` |

## Форматы отчётов

| Переменная | Описание |
|------------|----------|
| `DEFAULT_OUTPUT_FORMAT` | `pdf` |
| `ALLOWED_OUTPUT_FORMATS` | Список через запятую |
| `NOTION_INTEGRATION_TOKEN` | Notion |
| `NOTION_DATABASE_ID` | ID базы |
| `GOOGLE_SERVICE_ACCOUNT_JSON` | Путь к JSON |
| `GOOGLE_SLIDES_TEMPLATE_ID` | ID шаблона |

## SMTP

| Переменная | Описание |
|------------|----------|
| `SMTP_HOST`, `SMTP_PORT` | Сервер |
| `SMTP_USER`, `SMTP_PASSWORD` | Auth |
| `SMTP_FROM` | From header |
| `SMTP_USE_TLS` | `true` |

## Traefik / TLS

| Переменная | Описание |
|------------|----------|
| `DOMAIN` | Поддомен ReportAgent |
| `LETSENCRYPT_EMAIL` | ACME email |
| `TRAEFIK_ENABLED` | `true` / `false` |
| `ACME_CA_SERVER` | Let's Encrypt URL |

## Observability

| Переменная | Описание |
|------------|----------|
| `PROMETHEUS_RETENTION_DAYS` | `15` |
| `GRAFANA_ADMIN_USER` | `admin` |
| `GRAFANA_ADMIN_PASSWORD` | Пароль |
| `GRAFANA_DOMAIN` | Поддомен Grafana |
| `TELEGRAM_BOT_TOKEN` | Алерты |
| `TELEGRAM_CHAT_ID` | Chat ID |
| `ALERTS_ENABLED` | `true` |
| `OBSERVABILITY_HOST_METRICS` | `false` на слабом VPS |

## Self-healing

| Переменная | По умолчанию |
|------------|--------------|
| `SELF_HEALING_ENABLED` | `true` |
| `CHROMA_PERSIST_DIR` | `./chroma_data` |
| `SIMILARITY_THRESHOLD` | `0.75` |
| `SELF_HEALING_MIN_RAM_MB` | `512` |

## Admin

| Переменная | Описание |
|------------|----------|
| `ADMIN_API_KEY` | Ключ `/admin/*` |
| `ADMIN_ALLOWED_IPS` | IP whitelist |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `100` |

## Webhooks

| Переменная | По умолчанию |
|------------|--------------|
| `WEBHOOK_ENABLED` | `true` |
| `WEBHOOK_PUBLIC_BASE_URL` | `https://DOMAIN` |
| `WEBHOOK_TIMEOUT_SECONDS` | `10` |

## Биллинг

| Переменная | Описание |
|------------|----------|
| `BILLING_ENABLED` | `false` = без лимитов |
| `STRIPE_*` | Stripe keys и price IDs |
| `YOOKASSA_*` | ЮKassa |
| `FREEMIUM_REPORTS_LIMIT` | `5` |
| `PREMIUM_REPORTS_LIMIT` | `100` |
| `ENTERPRISE_REPORTS_LIMIT` | `1000` |

## SEO

| Переменная | Описание |
|------------|----------|
| `SITE_URL` | Canonical URL |
| `GA4_MEASUREMENT_ID` | Google Analytics |
| `YANDEX_METRIKA_ID` | Яндекс.Метрика |
