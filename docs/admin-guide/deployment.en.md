# Deployment (Admin)

Quick guide for deploying ReportAgent on a VPS.

## Modes

| Mode | `TRAEFIK_ENABLED` | When to use |
|------|-------------------|-------------|
| **Traefik** | `true` | ReportAgent owns ports 80/443 |
| **Standalone** | `false` | Ports taken (shared nginx), API on `:8000` |

## Quick deploy

```bash
cp .env.example .env
chmod +x deploy.sh scripts/build-docs.sh
./scripts/build-docs.sh
./deploy.sh
```

## Verify

```bash
curl https://your-domain/health
curl https://your-domain/help/
```

See [Docker](../deployment/docker.md), [VPS](../deployment/vps.md), [Environment variables](../deployment/environment-variables.md).
