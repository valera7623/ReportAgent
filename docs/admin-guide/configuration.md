# Конфигурация

Основные группы настроек в `.env`.

## Обязательные (production)

| Переменная | Описание |
|------------|----------|
| `DOMAIN` | Поддомен ReportAgent |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `SMTP_*` | Email (регистрация, отчёты) |
| `FRONTEND_URL` | `https://домен/app` |
| `ADMIN_API_KEY` | Ключ админ-API |

## OpenAI / голос

| Переменная | Описание |
|------------|----------|
| `OPENAI_API_KEY` | Whisper + GPT intent |
| `OPENAI_BASE_URL` | ProxyAPI для РФ |
| `VOICE_ENABLED` | `true` / `false` |

## Форматы отчётов

| Переменная | Описание |
|------------|----------|
| `DEFAULT_OUTPUT_FORMAT` | `pdf` |
| `ALLOWED_OUTPUT_FORMATS` | Список через запятую |
| `NOTION_*`, `GOOGLE_*` | Внешние интеграции |

## Observability

| Переменная | Описание |
|------------|----------|
| `GRAFANA_DOMAIN` | Поддомен Grafana |
| `GRAFANA_ADMIN_PASSWORD` | Пароль + basic auth |
| `TELEGRAM_BOT_TOKEN` | Алерты |
| `TELEGRAM_CHAT_ID` | Chat ID |
| `OBSERVABILITY_HOST_METRICS` | `false` на слабом VPS |

## Self-healing

| Переменная | По умолчанию |
|------------|--------------|
| `SELF_HEALING_ENABLED` | `true` |
| `CHROMA_PERSIST_DIR` | `./chroma_data` |
| `SIMILARITY_THRESHOLD` | `0.75` |

## Webhooks

| Переменная | Описание |
|------------|----------|
| `WEBHOOK_ENABLED` | `true` |
| `WEBHOOK_PUBLIC_BASE_URL` | Базовый URL в payload |

## Биллинг

Stripe (`STRIPE_*`) — основной. ЮKassa (`YOOKASSA_*`) — опционально для РФ.

Полный справочник: [Переменные окружения](../deployment/environment-variables.md)

## После изменений

```bash
./deploy.sh
```
