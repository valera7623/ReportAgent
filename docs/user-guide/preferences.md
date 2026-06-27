# Настройки пользователя

Preferences сохраняются в SQLite и применяются ко всем новым отчётам.

## Поля

| Поле | Значения | Эффект |
|------|----------|--------|
| `preferred_chart_type` | `bar`, `line`, `pie` | Тип графиков |
| `theme` | `light`, `dark` | Цветовая схема графиков |
| `default_email` | email | Email по умолчанию |
| `company_logo_url` | URL | Логотип в PDF |
| `timezone` | IANA, напр. `UTC` | Метаданные |
| `default_output_format` | `pdf`, `excel`, `pptx`, `notion`, `google_slides` | Формат по умолчанию |

## Через веб

**Настройки** → `/app#/preferences`

## Через API

```bash
# Получить
curl https://ваш-домен/api/preferences -H "X-API-Key: $API_KEY"

# Обновить
curl -X PUT https://ваш-домен/api/preferences \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "theme": "dark",
    "preferred_chart_type": "pie",
    "default_email": "user@example.com"
  }'

# Сбросить
curl -X DELETE https://ваш-домен/api/preferences \
  -H "X-API-Key: $API_KEY"
```

## Формат по умолчанию

```bash
curl -X POST https://ваш-домен/api/preferences/output_format \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"default_output_format": "excel"}'
```

Новые пользователи получают `DEFAULT_PREFERRED_CHART_TYPE` из `.env` (по умолчанию `bar`).
