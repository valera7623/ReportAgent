# Форматы отчётов

ReportAgent поддерживает пять форматов вывода.

!!! note "Beta: Notion / Google Slides"
    Экспорт в Notion и Google Slides работает в режиме **beta**: текстовые блоки и метаданные готовы; встраивание PNG-графиков ограничено. Для production-отчётов рекомендуем PDF, Excel или PPTX.

## Поддерживаемые форматы

| Формат | Значение `output_format` | Результат |
|--------|--------------------------|-----------|
| PDF | `pdf` | PDF с графиками (по умолчанию) |
| Excel | `excel` | `.xlsx` с листами данных и графиками |
| PowerPoint | `pptx` | Презентация `.pptx` |
| Notion | `notion` | Страница в базе Notion |
| Google Slides | `google_slides` | Презентация в Google Drive |

Список доступных форматов настраивается через `ALLOWED_OUTPUT_FORMATS` в `.env`.

## Установить формат по умолчанию

Веб: **Настройки** → формат по умолчанию

API:

```bash
curl -X POST https://ваш-домен/api/preferences/output_format \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"default_output_format": "excel"}'
```

## Примеры

=== "PDF"

    ```bash
    curl -X POST https://ваш-домен/generate_report \
      -H "X-API-Key: $API_KEY" \
      -F "file=@sales.csv"
    # → GET /tasks/{id}/pdf
    ```

=== "Excel"

    ```bash
    curl -X POST https://ваш-домен/generate_report \
      -H "X-API-Key: $API_KEY" \
      -F "file=@sales.csv" \
      -F "output_format=excel"
    # → GET /tasks/{id}/export
    ```

=== "PowerPoint"

    ```bash
    curl -X POST https://ваш-домен/generate_report \
      -H "X-API-Key: $API_KEY" \
      -F "file=@sales.csv" \
      -F "output_format=pptx"
    ```

=== "Notion"

    Требует `NOTION_INTEGRATION_TOKEN` и `NOTION_DATABASE_ID`.

    ```bash
    curl -X POST https://ваш-домен/generate_report \
      -H "X-API-Key: $API_KEY" \
      -F "sheets_url=https://docs.google.com/spreadsheets/d/..." \
      -F "output_format=notion"
    ```

=== "Google Slides"

    Требует `secrets/google-sa.json` и `GOOGLE_SLIDES_TEMPLATE_ID`.

    ```bash
    curl -X POST https://ваш-домен/generate_report \
      -H "X-API-Key: $API_KEY" \
      -F "file=@sales.csv" \
      -F "output_format=google_slides"
    ```

## Настройка Notion

1. Создайте интеграцию: https://www.notion.so/my-integrations
2. Скопируйте **Internal Integration Token** → `NOTION_INTEGRATION_TOKEN`
3. Создайте базу, подключите интеграцию (Share → Invite)
4. Получите `database_id`:

```bash
NOTION_INTEGRATION_TOKEN=secret_... python3 scripts/setup_notion.py
```

## Настройка Google Slides

1. Google Cloud Console → включите **Google Slides API** и **Google Drive API**
2. Создайте сервисный аккаунт → JSON → `secrets/google-sa.json`
3. Создайте шаблон с плейсхолдерами `%DATE%`, `%METRICS%`, `%CHART_1%`
4. Поделитесь шаблоном с email сервисного аккаунта (Editor)
5. ID из URL → `GOOGLE_SLIDES_TEMPLATE_ID`

## Голосом

Intent parser распознаёт формат из речи: «сделай в Excel», «отправь в Notion», «создай презентацию».

## Тест

```bash
python3 scripts/test_formats.py
```
