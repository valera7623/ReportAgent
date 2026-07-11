# FAQ

## Общие

### Что такое ReportAgent?

Micro-SaaS для автоматической генерации аналитических отчётов с графиками из CSV, Excel и Google Sheets.

### Нужен ли OpenAI?

Для **голосового ввода** — да (`OPENAI_API_KEY`). Для обычных отчётов из файлов — нет.

### Какие форматы отчётов?

PDF, Excel, PowerPoint — **готово**. Notion и Google Slides — **beta** (базовый экспорт; встраивание графиков ограничено).

### Что готово / beta / roadmap?

См. таблицу в [README](../README.md) и [roadmap](roadmap.md).

## Регистрация и ключи

### Не приходит письмо подтверждения

Проверьте `SMTP_*` и `EMAIL_FROM` в `.env`. Проверьте spam.

### Потерял API-ключ

Полный ключ не восстанавливается. Создайте новый через `/app#/keys` или ротируйте существующий.

### Можно ли работать без регистрации?

Локально: `DISABLE_AUTH=true`. Production — только с API-ключом.

## Отчёты

### Долго генерируется отчёт

Обычно 5–30 секунд. Проверьте Celery worker: `docker logs reportagent_celery_worker`.

### Google Sheets не читается

Таблица должна быть **публичной** (Anyone with the link → Viewer).

### Ошибка ParserError в CSV

Попробуйте другой разделитель (`;` vs `,`) или сохраните как UTF-8. Self-healing может исправить автоматически.

## Голос

### Whisper 401 / пустой transcript

Для ProxyAPI.ru нужен `OPENAI_BASE_URL=https://api.proxyapi.ru/openai/v1`.

### curl error 26

Файл аудио не найден — проверьте путь к `@recording.m4a`.

## Деплой

### curl localhost:8000 refused на VPS

В режиме standalone API не проброшен на хост. Используйте поддомен или `docker exec reportagent_fastapi curl localhost:8000/health`.

### Где документация?

- `/help/` — MkDocs (руководства)
- `/docs` — Swagger (API)

## Документация MkDocs

```bash
pip install -r docs/requirements-docs.txt
mkdocs serve
```

Сборка: `./scripts/build-docs.sh`
