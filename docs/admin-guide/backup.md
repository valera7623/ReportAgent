# Резервное копирование

## Что сохранять

| Путь | Содержимое | Критичность |
|------|------------|-------------|
| `app/data/users.db` | Пользователи, ключи, история | **Высокая** |
| `storage/pdfs/` | Сгенерированные PDF и графики | Средняя |
| `storage/formatted/` | Excel, PPTX | Средняя |
| `storage/uploads/` | Загруженные исходники | Низкая |
| `chroma_data/` | База знаний self-healing | Средняя |
| `secrets/` | Google SA, другие ключи | **Высокая** |
| `.env` | Конфигурация и секреты | **Высокая** |

!!! warning "Не коммитьте в git"
    `.env`, `users.db`, `storage/`, `secrets/` — только бэкап на диск/S3.

## Ручной бэкап

```bash
BACKUP_DIR=~/backups/reportagent-$(date +%Y%m%d)
mkdir -p "$BACKUP_DIR"

cp app/data/users.db "$BACKUP_DIR/"
cp .env "$BACKUP_DIR/"
tar czf "$BACKUP_DIR/storage.tar.gz" storage/
tar czf "$BACKUP_DIR/chroma_data.tar.gz" chroma_data/ 2>/dev/null || true
tar czf "$BACKUP_DIR/secrets.tar.gz" secrets/ 2>/dev/null || true
```

## Восстановление

```bash
./deploy.sh down   # или docker compose down
cp backup/users.db app/data/
tar xzf backup/storage.tar.gz
tar xzf backup/chroma_data.tar.gz
./deploy.sh
```

## Рекомендуемый cron

```cron
0 3 * * * /home/smdg/ReportAgent/scripts/backup.sh
```

Создайте `scripts/backup.sh` по образцу ручного бэкапа выше.

## Redis

Данные Celery (результаты задач) — ephemeral. Redis persistence через Docker volume `redis-data`; для disaster recovery достаточно перезапуска очереди.

## Grafana / Prometheus

Дашборды provisioning в git (`grafana/`). Метрики Prometheus — не персистентны критично; retention задаётся `PROMETHEUS_RETENTION_DAYS`.
