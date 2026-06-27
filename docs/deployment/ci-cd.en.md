# CI/CD

GitHub Actions in `.github/workflows/`.

## Workflows

| Workflow | Trigger | Purpose |
|----------|---------|---------|
| `ci.yml` | Pull Request | Tests, compileall |
| `deploy-vps.yml` | Push to main | CI + SSH deploy |

## Secrets

`VPS_HOST`, `VPS_USER`, `VPS_SSH_PRIVATE_KEY`, `GIT_DEPLOY_TOKEN`

## Deploy flow

```
push main → CI → SSH VPS → git pull → build-docs → deploy.sh
```

## Not synced via git

`.env`, `app/data/*.db`, `storage/`, `logs/`
