# Grafana за smdg-nginx (когда открывается SMDG вместо Grafana)

## Симптом

`https://grafana.reportagent.fileguardian.info/` показывает **SMDG**, а не Grafana.

**Причина:** в nginx **нет** `server_name grafana.reportagent.fileguardian.info`. Запрос попадает в **default server** (SMDG на `fileguardian.info`).

---

## Шаг 1 — Grafana в сети nginx

На VPS в `~/ReportAgent/.env`:

```bash
TRAEFIK_ENABLED=false
EXTERNAL_NGINX_NETWORK=smdg_frontend
DOMAIN=reportagent.fileguardian.info
GRAFANA_DOMAIN=grafana.reportagent.fileguardian.info
```

```bash
cd ~/ReportAgent && ./deploy.sh
```

Проверка **из nginx-контейнера** (имя может отличаться):

```bash
NGINX=$(docker ps --format '{{.Names}}' | grep -i nginx | head -1)
echo "nginx container: $NGINX"

docker exec "$NGINX" curl -s http://reportagent_grafana:3000/api/health
# ожидается: {"commit":"...","database":"ok",...}
```

Если `Could not resolve host` — Grafana не в сети `smdg_frontend`. Проверьте:

```bash
docker inspect reportagent_grafana --format '{{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}'
# должно быть: reportagent_internal smdg_frontend
```

---

## Шаг 2 — Найти конфиг nginx SMDG

```bash
NGINX=$(docker ps --format '{{.Names}}' | grep -i nginx | head -1)

# где лежат конфиги внутри контейнера
docker exec "$NGINX" ls -la /etc/nginx/conf.d/
docker exec "$NGINX" cat /etc/nginx/nginx.conf | head -30

# откуда смонтированы конфиги на хосте
docker inspect "$NGINX" --format '{{json .Mounts}}' | python3 -m json.tool
```

Обычно конфиги SMDG лежат в `~/smdg/...` или рядом — правьте файл на **хосте**, затем reload nginx.

---

## Шаг 3 — Добавить server block для Grafana

Создайте файл, например `grafana-reportagent.conf` (рядом с конфигом reportagent):

```nginx
# HTTP → HTTPS
server {
    listen 80;
    server_name grafana.reportagent.fileguardian.info;
    return 301 https://$host$request_uri;
}

# HTTPS → Grafana container
server {
    listen 443 ssl http2;
    server_name grafana.reportagent.fileguardian.info;

    # Пути к сертификату — как у reportagent или отдельный certbot:
    ssl_certificate     /etc/letsencrypt/live/grafana.reportagent.fileguardian.info/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/grafana.reportagent.fileguardian.info/privkey.pem;

    location / {
        proxy_pass http://reportagent_grafana:3000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

**Важно:** `server_name` должен быть **точно** `grafana.reportagent.fileguardian.info`, не `fileguardian.info`.

Если сертификата ещё нет — временно только HTTP (для теста):

```nginx
server {
    listen 80;
    server_name grafana.reportagent.fileguardian.info;
    location / {
        proxy_pass http://reportagent_grafana:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

---

## Шаг 4 — TLS-сертификат для поддомена

```bash
# пример webroot (путь webroot как в smdg certbot)
sudo certbot certonly --webroot -w /var/www/certbot \
  -d grafana.reportagent.fileguardian.info
```

Или добавьте домен к существующему multi-domain cert, если так настроен smdg.

Проверка сертификата:

```bash
echo | openssl s_client -connect grafana.reportagent.fileguardian.info:443 -servername grafana.reportagent.fileguardian.info 2>/dev/null | openssl x509 -noout -subject -dates
```

---

## Шаг 5 — Reload nginx

```bash
NGINX=$(docker ps --format '{{.Names}}' | grep -i nginx | head -1)
docker exec "$NGINX" nginx -t
docker exec "$NGINX" nginx -s reload
```

---

## Шаг 6 — Проверка

```bash
curl -s http://grafana.reportagent.fileguardian.info/api/health
curl -s https://grafana.reportagent.fileguardian.info/api/health

# должен быть JSON Grafana, не HTML SMDG:
# {"database":"ok",...}
```

В браузере: логин Grafana — `admin` / `GRAFANA_ADMIN_PASSWORD` из `~/ReportAgent/.env`.

Дашборд: `/d/ReportAgent-Main/reportagent-main`

---

## Частые ошибки

| Симптом | Решение |
|---------|---------|
| Открывается SMDG | Нет `server_name grafana.reportagent...` в nginx |
| SSL hostname mismatch | Отдельный cert + server block на 443 |
| 502 Bad Gateway | `reportagent_grafana` не в сети nginx → `./deploy.sh` |
| Редирект на SMDG | default server перехватывает — добавьте явный server block |
