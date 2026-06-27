# Preview Before Send

Before generating the full report you can view a **preview**: table (first 50 rows), basic statistics, and charts.

## Flow

1. `POST /api/reports/preview` — upload file or Google Sheets URL
2. Response: `preview_id`, `data`, `expires_at`
3. Charts: `GET /api/preview/chart/{preview_id}/{chart_index}` (PNG)
4. Change chart type: `POST /api/reports/preview/regenerate-chart`
5. Confirm: `POST /api/reports/preview/confirm` → full generation

!!! note "TTL"
    Preview is stored in Redis for **1 hour** and is **not** added to history until confirmed.

## API example

```bash
curl -X POST https://your-domain/api/reports/preview \
  -H "X-API-Key: $API_KEY" \
  -F "file=@sample_sales.csv"

curl -X POST https://your-domain/api/reports/preview/confirm \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"preview_id":"uuid","output_format":"pdf"}'
```

## Large files (> 10 MB)

Processed asynchronously via Celery. Poll `GET /api/reports/preview/status/{job_id}`.

## Web UI

Dashboard → «New report» modal with table, charts, and confirm button.

## API reference

[Preview API](../api/preview.md)
