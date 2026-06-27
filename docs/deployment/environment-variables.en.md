# Environment Variables

Full reference from `.env.example`. See Russian version for complete tables.

## Key groups

- **Auth**: `JWT_SECRET_KEY`, `EMAIL_FROM`, `FRONTEND_URL`
- **Database**: `DATABASE_URL` (SQLite)
- **OpenAI/Voice**: `OPENAI_API_KEY`, `VOICE_ENABLED`
- **Output formats**: `DEFAULT_OUTPUT_FORMAT`, `NOTION_*`, `GOOGLE_*`
- **SMTP**: `SMTP_HOST`, `SMTP_*`
- **Traefik**: `DOMAIN`, `TRAEFIK_ENABLED`
- **Observability**: `GRAFANA_*`, `TELEGRAM_*`
- **Self-healing**: `SELF_HEALING_ENABLED`, `CHROMA_PERSIST_DIR`
- **Admin**: `ADMIN_API_KEY`
- **Billing**: `STRIPE_*`, `YOOKASSA_*`, `FREEMIUM_REPORTS_LIMIT`

Copy `.env.example` to `.env` and edit before deploy.
