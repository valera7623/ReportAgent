# ReportAgent Frontend (HTML / CSS / JS)

Лёгкий статический дашборд **без npm, без сборки, без React**.

## Запуск

### Вариант 1 — через FastAPI (рекомендуется)

Бэкенд отдаёт фронтенд по адресу:

**http://localhost:8000/app/**

```bash
./deploy-dev.sh   # или ваш способ запуска API
```

Откройте в браузере `/app/` и войдите с API-ключом.

### Вариант 2 — любой статический сервер

```bash
cd frontend
python3 -m http.server 8080
```

Откройте http://localhost:8080 — в `js/config.js` задайте API:

```html
<script>window.REPORTAGENT_API_BASE = 'http://localhost:8000';</script>
```

(добавьте в `index.html` перед `app.js`, если API на другом origin)

## Структура

```
frontend/
├── index.html          # SPA-оболочка + SEO meta
├── robots.txt
├── sitemap.xml
├── og-image.png
├── favicon.ico
├── css/styles.css      # Стили + тёмная тема
└── js/
    ├── app.js          # Точка входа
    ├── seo.js          # Динамические meta + JSON-LD
    ├── api.js          # Fetch + все эндпоинты
    ├── state.js        # Auth, тема (localStorage)
    ├── router.js       # Hash-роутинг (#/dashboard)
    ├── layout.js       # Сайдбар + хедер
    ├── ui.js           # Toast, модалки
    ├── utils/
    │   └── analytics.js  # GA4 + Yandex Metrika
    ├── utils.js
    ├── config.js
    └── pages/          # Страницы
```

## Зависимости

Только **Chart.js** с CDN (круговая диаграмма на дашборде). Всё остальное — нативный JS.

## Функционал

Тот же набор, что и в React-версии:

- Логин по API-ключу (`reportagent_api_key` в localStorage)
- Дашборд, отчёты, ключи, вебхуки, настройки
- Админ-панель (users, health, celery, self-healing, logs)
- Тёмная/светлая тема, адаптивный сайдбар
- 401 → выход и редирект на логин

## Авторизация

Все запросы с заголовком `X-API-Key`. Админ определяется успешным `GET /admin/health/all`.

## Примечания

- Роутинг через hash (`#/reports`) — работает без настройки nginx
- Фильтры отчётов — на клиенте (бэкенд: только page/limit)
- Live stream логов — `fetch` + ReadableStream с `X-API-Key`

## SEO и аналитика

Фронтенд **без npm-сборки** — мета-теги и статика отдаются напрямую из `frontend/`.

### Файлы

| Файл | Назначение |
|------|------------|
| `index.html` | Базовые meta, Open Graph, Twitter Cards, JSON-LD |
| `js/seo.js` | Динамическое обновление title/OG при смене hash-роута |
| `js/utils/analytics.js` | Google Analytics 4 + Yandex Metrika, событие `page_view` |
| `robots.txt` | Правила индексации (также `GET /robots.txt` на корне домена) |
| `sitemap.xml` | Публичные URL (`GET /sitemap.xml`, домен из `DOMAIN` в `.env`) |
| `og-image.png`, `favicon*.png`, `favicon.ico` | Превью для соцсетей и иконки |

### Настройка на VPS

1. В корневом `.env` задайте:
   ```bash
   DOMAIN=reportagent.example.com
   GA4_MEASUREMENT_ID=G-XXXXXXXXXX
   YANDEX_METRIKA_ID=12345678
   ```
2. При деплое `./deploy.sh` автоматически вызывает `./scripts/inject-frontend-seo.sh`.
   Вручную (без полного деплоя):
   ```bash
   ./scripts/inject-frontend-seo.sh
   ```
3. Перегенерировать OG/favicon (опционально):
   ```bash
   python3 scripts/generate_seo_assets.py
   ```

### Проверка

- Вкладка браузера: заголовок меняется при `#/pricing`, `#/login`
- `curl https://ваш-домен/robots.txt`
- `curl https://ваш-домен/sitemap.xml`
- Превью в Telegram/VK: ссылка на `https://ваш-домен/app/` (OG из `index.html`)
- [Google Rich Results Test](https://search.google.com/test/rich-results) — JSON-LD
- Google Search Console / Яндекс.Вебмастер — добавьте сайт и sitemap

### Ограничения hash-SPA

Соцсети и часть ботов **не выполняют JS** — для шаринга важны статические теги в `index.html`. Динамические meta в `seo.js` улучшают вкладку браузера и GA/Метрику при навигации.

