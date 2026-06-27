# API — Preview

## POST /api/reports/preview

Create preview from `file` or `sheets_url`.

## GET /api/preview/chart/{preview_id}/{chart_index}

PNG chart image.

## POST /api/reports/preview/confirm

Confirm and start full report generation.

## GET /api/reports/preview/status/{job_id}

Async preview status for large files (> 10 MB).
