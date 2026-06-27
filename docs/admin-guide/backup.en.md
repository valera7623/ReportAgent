# Backup

## What to back up

| Path | Content | Priority |
|------|---------|----------|
| `app/data/users.db` | Users, keys, history | **High** |
| `storage/` | Generated reports | Medium |
| `chroma_data/` | Self-healing knowledge base | Medium |
| `secrets/` | Service account keys | **High** |
| `.env` | Configuration | **High** |

## Manual backup

```bash
BACKUP_DIR=~/backups/reportagent-$(date +%Y%m%d)
mkdir -p "$BACKUP_DIR"
cp app/data/users.db "$BACKUP_DIR/"
cp .env "$BACKUP_DIR/"
tar czf "$BACKUP_DIR/storage.tar.gz" storage/
```

## Restore

Stop stack, restore files, run `./deploy.sh`.
