# API — Отчёты

## POST /generate_report

Multipart form. Требует `X-API-Key`.

| Поле | Тип | Обязательно | Описание |
|------|-----|-------------|----------|
| `file` | file | no* | CSV, xlsx, xls |
| `sheets_url` | string | no* | Google Sheets URL |
| `email` | string | no | Email доставки |
| `output_format` | string | no | pdf, excel, pptx, notion, google_slides |

\* Укажите **либо** `file`, **либо** `sheets_url`.

```bash
curl -X POST https://ваш-домен/generate_report \
  -H "X-API-Key: $API_KEY" \
  -F "file=@sales.csv" \
  -F "output_format=pdf"
```

**Ответ 202:**

```json
{
  "task_id": "abc-123",
  "status": "queued",
  "download_url": "/tasks/abc-123/pdf",
  "output_format": "pdf",
  "usage_count": 1
}
```

## GET /tasks/{task_id}

Статус Celery-задачи.

## GET /tasks/{task_id}/pdf

Скачать PDF (legacy, обратная совместимость).

## GET /tasks/{task_id}/export

Excel, PPTX или redirect на Notion/Slides.

## GET /api/dashboard/stats

Статистика за 30 дней.

## GET /api/reports

История отчётов (пагинация `page`, `limit`).

## DELETE /api/reports/{task_id}

Удалить отчёт и файлы (только свои).

## GET /samples/sample_sales.csv

Тестовый CSV.
