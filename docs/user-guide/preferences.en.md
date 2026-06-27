# User Preferences

Preferences are stored in SQLite and apply to all new reports.

## Fields

| Field | Values | Effect |
|-------|--------|--------|
| `preferred_chart_type` | `bar`, `line`, `pie` | Chart type |
| `theme` | `light`, `dark` | Chart color scheme |
| `default_email` | email | Default delivery email |
| `company_logo_url` | URL | Logo in PDF |
| `timezone` | IANA e.g. `UTC` | Metadata |
| `default_output_format` | `pdf`, `excel`, … | Default report format |

## API

```bash
curl https://your-domain/api/preferences -H "X-API-Key: $API_KEY"

curl -X PUT https://your-domain/api/preferences \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"theme": "dark", "preferred_chart_type": "pie"}'
```

Web UI: `/app#/preferences`
