# VPS Deployment

## Server prep

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
```

## Mode A — Traefik

```bash
TRAEFIK_ENABLED=true
./scripts/build-docs.sh && ./deploy.sh
```

## Mode B — External nginx (SMDG)

```bash
TRAEFIK_ENABLED=false
DOMAIN=reportagent.fileguardian.info
```

See `docs/smdg-edge-proxy.example.conf`

## Sync from GitHub

```bash
./scripts/sync-pull.sh --deploy
```
