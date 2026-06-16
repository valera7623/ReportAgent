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
├── index.html          # SPA-оболочка
├── css/styles.css      # Стили + тёмная тема
└── js/
    ├── app.js          # Точка входа
    ├── api.js          # Fetch + все эндпоинты
    ├── state.js        # Auth, тема (localStorage)
    ├── router.js       # Hash-роутинг (#/dashboard)
    ├── layout.js       # Сайдбар + хедер
    ├── ui.js           # Toast, модалки
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
