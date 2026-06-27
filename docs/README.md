# ReportAgent Documentation

Полная документация платформы ReportAgent — micro-SaaS для генерации отчётов (PDF, Excel, PowerPoint, Notion, Google Slides) из CSV/Excel и Google Sheets.

## Быстрый старт

```bash
pip install -r docs/requirements-docs.txt
mkdocs serve
```

Откройте http://127.0.0.1:8000

## Сборка сайта

```bash
./scripts/build-docs.sh
# или: mkdocs build
# Результат: site/
```

## Структура

| Раздел | Аудитория | Описание |
|--------|-----------|----------|
| [user-guide/](user-guide/) | Пользователи | Регистрация, отчёты, превью, голос, подписка |
| [admin-guide/](admin-guide/) | DevOps, админы | Деплой, конфигурация, мониторинг, бэкапы |
| [developer-guide/](developer-guide/) | Разработчики | Архитектура, БД, агенты, self-healing |
| [api/](api/) | Интеграторы | REST API с примерами curl |
| [deployment/](deployment/) | DevOps | Docker, VPS, CI/CD, переменные окружения |
| [misc/](misc/) | Все | Changelog, FAQ, глоссарий |

## Языки / Languages

| Язык | URL |
|------|-----|
| Русский (по умолчанию) | `/help/` |
| English | `/help/en/` |

Переключатель языка — в шапке сайта (Material). При первом визите язык определяется автоматически по настройкам браузера.

## Интерактивная API-документация

| URL | Описание |
|-----|----------|
| `/docs` | Swagger UI (OpenAPI) |
| `/help/` | Руководства пользователя, админа, разработчика (MkDocs) |

На проде: `https://reportagent.fileguardian.info/help/`
