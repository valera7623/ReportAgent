# API — Reports

## POST /generate_report

Multipart form. Requires `X-API-Key`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `file` | file | no* | CSV, xlsx, xls |
| `sheets_url` | string | no* | Google Sheets URL |
| `email` | string | no | Delivery email |
| `output_format` | string | no | pdf, excel, pptx, notion, google_slides |

## GET /tasks/{task_id}

Celery task status.

## GET /tasks/{task_id}/pdf

Download PDF.

## GET /tasks/{task_id}/export

Excel, PPTX, or redirect to Notion/Slides.

## GET /api/reports

Report history with pagination.

## DELETE /api/reports/{task_id}

Delete report and files (own reports only).
