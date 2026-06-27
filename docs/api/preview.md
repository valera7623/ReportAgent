# API — Превью

## POST /api/reports/preview

Создать превью. Form-data: `file` или `sheets_url`.

```bash
curl -X POST https://ваш-домен/api/reports/preview \
  -H "X-API-Key: $API_KEY" \
  -F "file=@sample_sales.csv"
```

**Ответ:**

```json
{
  "preview_id": "uuid",
  "data": {
    "headers": ["date", "revenue"],
    "rows": [["2026-01-01", "1000"]],
    "summary": {"row_count": 100},
    "charts": [{"type": "bar", "title": "Revenue"}]
  },
  "expires_at": "2026-01-15T11:00:00Z"
}
```

## GET /api/preview/chart/{preview_id}/{chart_index}

PNG-график.

## POST /api/reports/preview/regenerate-chart

```json
{"preview_id": "uuid", "chart_index": 0, "chart_type": "pie"}
```

## POST /api/reports/preview/confirm

```json
{"preview_id": "uuid", "output_format": "pdf", "email": "user@example.com"}
```

Запускает полную генерацию отчёта.

## GET /api/reports/preview/status/{job_id}

Статус асинхронного превью (файлы > 10 MB).
