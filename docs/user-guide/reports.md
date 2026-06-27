# Создание отчётов

## Источники данных

Укажите **один** из источников:

| Источник | Поле формы | Форматы |
|----------|------------|---------|
| Файл | `file` | CSV, `.xlsx`, `.xls` |
| Google Sheets | `sheets_url` | Публичная ссылка |

## Через веб-интерфейс

1. Откройте **Дашборд** → блок «Новый отчёт»
2. Загрузите файл или вставьте URL Google Sheets
3. Выберите формат (или используйте настройку по умолчанию)
4. Опционально: email для доставки
5. Нажмите **Сгенерировать**

Статус задачи обновляется автоматически. По готовности — ссылка на скачивание.

## Через API

```bash
curl -X POST https://ваш-домен/generate_report \
  -H "X-API-Key: $API_KEY" \
  -F "file=@data/sales.csv" \
  -F "output_format=pdf" \
  -F "email=reports@company.com"
```

Ответ `202`:

```json
{
  "task_id": "abc-123",
  "status": "queued",
  "download_url": "/tasks/abc-123/pdf",
  "output_format": "pdf"
}
```

## Статус задачи

```bash
curl -H "X-API-Key: $API_KEY" \
  https://ваш-домен/tasks/abc-123
```

| Статус | Значение |
|--------|----------|
| `PENDING` | В очереди |
| `STARTED` | Генерируется |
| `SUCCESS` | Готово — скачайте по `download_url` |
| `FAILURE` | Ошибка — см. поле `error` |
| `NEEDS_CLARIFICATION` | Голосовой запрос требует уточнения |

## Скачивание

| Формат | Эндпоинт |
|--------|----------|
| PDF | `GET /tasks/{id}/pdf` |
| Excel, PPTX | `GET /tasks/{id}/export` |
| Notion, Google Slides | `GET /tasks/{id}/export` → redirect 302 |

## Google Sheets

Таблица должна быть **доступна по ссылке** (Anyone with the link → Viewer):

```bash
curl -X POST https://ваш-домен/generate_report \
  -H "X-API-Key: $API_KEY" \
  -F "sheets_url=https://docs.google.com/spreadsheets/d/SPREADSHEET_ID/edit"
```

## Лимиты тарифа

Количество отчётов ограничено подпиской (см. [Подписка](subscription.md)). При превышении — HTTP 402.

## История отчётов

```bash
curl "https://ваш-домен/api/reports?page=1&limit=20" \
  -H "X-API-Key: $API_KEY"
```

Веб: **Отчёты** → `/app#/reports`

## Связанные разделы

- [Превью](preview.md) — предпросмотр перед полной генерацией
- [Форматы](output-formats.md) — PDF, Excel, PPTX, Notion, Slides
- [API отчётов](../api/reports.md)
