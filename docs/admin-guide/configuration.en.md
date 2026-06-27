# Configuration

Main `.env` setting groups.

## Required (production)

| Variable | Description |
|----------|-------------|
| `DOMAIN` | ReportAgent subdomain |
| `JWT_SECRET_KEY` | `openssl rand -hex 32` |
| `SMTP_*` | Email (registration, reports) |
| `FRONTEND_URL` | `https://domain/app` |
| `ADMIN_API_KEY` | Admin API key |

Full reference: [Environment variables](../deployment/environment-variables.md)

After changes: `./deploy.sh`
