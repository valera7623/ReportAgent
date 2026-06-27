# Creating Reports

## Data sources

Provide **one** source:

| Source | Form field | Formats |
|--------|------------|---------|
| File | `file` | CSV, `.xlsx`, `.xls` |
| Google Sheets | `sheets_url` | Public URL |

## Via web UI

1. Open **Dashboard** → «New report»
2. Upload a file or paste a Google Sheets URL
3. Choose output format (or use default preference)
4. Optional: delivery email
5. Click **Generate**

Task status updates automatically. When ready — download link appears.

## Via API

```bash
curl -X POST https://your-domain/generate_report \
  -H "X-API-Key: $API_KEY" \
  -F "file=@data/sales.csv" \
  -F "output_format=pdf" \
  -F "email=reports@company.com"
```

Response `202`:

```json
{
  "task_id": "abc-123",
  "status": "queued",
  "download_url": "/tasks/abc-123/pdf",
  "output_format": "pdf"
}
```

## Task status

```bash
curl -H "X-API-Key: $API_KEY" \
  https://your-domain/tasks/abc-123
```

| Status | Meaning |
|--------|---------|
| `PENDING` | Queued |
| `STARTED` | Generating |
| `SUCCESS` | Ready — download via `download_url` |
| `FAILURE` | Error — see `error` field |
| `NEEDS_CLARIFICATION` | Voice request needs clarification |

## Download

| Format | Endpoint |
|--------|----------|
| PDF | `GET /tasks/{id}/pdf` |
| Excel, PPTX | `GET /tasks/{id}/export` |
| Notion, Google Slides | `GET /tasks/{id}/export` → 302 redirect |

## Related

- [Preview](preview.md)
- [Output formats](output-formats.md)
- [Reports API](../api/reports.md)
