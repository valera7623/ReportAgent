# Output Formats

ReportAgent supports five output formats.

## Supported formats

| Format | `output_format` | Result |
|--------|-----------------|--------|
| PDF | `pdf` | PDF with charts (default) |
| Excel | `excel` | `.xlsx` with data sheets and charts |
| PowerPoint | `pptx` | `.pptx` presentation |
| Notion | `notion` | Page in Notion database |
| Google Slides | `google_slides` | Presentation in Google Drive |

Available formats are controlled by `ALLOWED_OUTPUT_FORMATS` in `.env`.

## Set default format

```bash
curl -X POST https://your-domain/api/preferences/output_format \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"default_output_format": "excel"}'
```

## Examples

```bash
# PDF (default)
curl -X POST https://your-domain/generate_report \
  -H "X-API-Key: $API_KEY" -F "file=@sales.csv"

# Excel
curl -X POST https://your-domain/generate_report \
  -H "X-API-Key: $API_KEY" -F "file=@sales.csv" -F "output_format=excel"
```

Notion and Google Slides require additional environment variables — see the Russian guide or `.env.example`.

## Test

```bash
python3 scripts/test_formats.py
```
