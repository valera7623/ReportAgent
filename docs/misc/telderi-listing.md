# ReportAgent — материалы для лота Telderi

> **Продаётся только исходный код.** Домен, VPS, пользователи, платёжные аккаунты и API-ключи покупателю не передаются.

---

## Заголовок лота

**ReportAgent — SaaS для автоматических отчётов из CSV/Excel (PDF, Excel, PPTX, API, биллинг Stripe/ЮKassa)**

Альтернатива (короче):

**ReportAgent v1.8 — AI-отчёты из таблиц: PDF/Excel/PPTX, голос, API, Stripe + ЮKassa**

---

## Краткое описание (до ~500 символов)

Готовый micro-SaaS: загрузка CSV/Excel → PDF/Excel/PPTX с графиками и AI-аналитикой. FastAPI + Celery + Redis, SPA, JWT/API keys, Stripe и ЮKassa, голосовой ввод, MkDocs `/help/`, Prometheus/Grafana. Демо на VPS. **В лот входит только исходный код** (GitHub), без домена, хостинга и пользователей.

---

## Полное описание (копировать в Telderi)

### Что это

**ReportAgent** — micro-SaaS для генерации бизнес-отчётов из CSV/Excel и Google Sheets. Пользователь загружает данные (или диктует задачу голосом) — система строит графики, пишет аналитический текст и отдаёт **PDF, Excel или PowerPoint**. Есть REST API, личный кабинет (SPA), документация RU/EN, подписки через **Stripe** и **ЮKassa**.

Версия **v1.8** — production-ready демо на отдельном VPS, CI/CD (GitHub Actions), smoke-тесты, мониторинг.

### Что входит в продажу

| Входит | Не входит |
|--------|-----------|
| Полный исходный код (репозиторий) | Домен `fileguardian.info` |
| Docker Compose (dev + prod) | VPS и данные на нём |
| MkDocs-документация, миграции БД | Пользователи и их данные |
| Скрипты деплоя, backup, healthcheck | Stripe / ЮKassa merchant-аккаунты |
| Grafana/Prometheus конфиги | OpenAI / SMTP credentials продакшена |

Покупатель разворачивает продукт на своём сервере со своими ключами и брендом.

### Стек и архитектура

- **Backend:** Python 3.11, FastAPI, Celery, Redis
- **Frontend:** Vanilla JS SPA (hash-router)
- **БД:** SQLite (есть задел под PostgreSQL)
- **Инфра:** Docker, Traefik (TLS), GitHub Actions deploy
- **AI:** OpenAI (анализ, Whisper для голоса)
- **Биллинг:** Stripe subscriptions + ЮKassa (разовая оплата периода)
- **Observability:** Prometheus, Grafana, Alertmanager → Telegram

### Готовые функции

- PDF / Excel / PPTX с графиками и брендингом (логотип, заголовок отчёта)
- Загрузка CSV/Excel, публичные Google Sheets
- Email/password + JWT, API keys, freemium-лимиты
- Админ API, audit log, preview-before-send
- Голосовой ввод (API + страница `/app#/voice`)
- Stripe и ЮKassa в UI
- Документация `/help/` (RU/EN), Swagger `/docs`
- Webhooks с дедупликацией, возврат слотов при ошибках генерации

### Beta / roadmap (честно)

- Notion / Google Slides — beta (текст + ссылки)
- OAuth Google/Microsoft — scaffold
- Scheduled reports — API есть, UI в SPA — нет
- PostgreSQL — helper, не полный production adapter

### Для кого лот

- Разработчик или студия, которая хочет **запустить свой report-SaaS** без разработки с нуля
- Агентство, которое внедрит white-label отчётность клиентам
- Покупатель с опытом Docker + один платёжный провайдер (Stripe или ЮKassa)

### Демо и просмотр

**Демо-сайт:** https://reportagent.fileguardian.info

| Раздел | URL |
|--------|-----|
| Личный кабинет | https://reportagent.fileguardian.info/app#/ |
| Тарифы (Stripe) | https://reportagent.fileguardian.info/app#/pricing |
| Тарифы (ЮKassa) | https://reportagent.fileguardian.info/app#/pricing-yookassa |
| Голос | https://reportagent.fileguardian.info/app#/voice |
| Документация | https://reportagent.fileguardian.info/help/ |
| API (Swagger) | https://reportagent.fileguardian.info/docs |

**Демо-доступ (для проверяющих на Telderi):**

- Логин: `telderi-demo@fileguardian.info`
- Пароль: *указать в поле «доступ к демо» или выдать в личных сообщениях после запроса*
- После входа: 5 бесплатных отчётов (freemium), можно загрузить `sample_sales.csv` из репозитория

Создание/сброс демо-аккаунта на своём инстансе:

```bash
docker exec reportagent_fastapi python scripts/setup_telderi_demo.py
```

### Репозиторий

Передаётся покупателю после сделки: `https://github.com/valera7623/ReportAgent` (ветка `master`).

### Почему продаю

*(выберите и отредактируйте)*

- Нет ресурсов на маркетинг и поддержку пользователей — продукт технически готов, фокус на других проектах.
- Продаю код как актив, чтобы покупатель развивал под своим брендом.

### Условия аукциона (рекомендация)

| Параметр | Значение |
|----------|----------|
| Стартовая / оптимальная цена | **250 000 ₽** |
| Блиц-цена | **420 000 ₽** |
| Срок | **7 дней** |
| Формат | Только исходный код, передача репозитория |

---

## Скриншоты (8–10 шт.)

Снимайте в браузере **1920×1080** или **1440×900**, без личных данных. Имена файлов — для загрузки на Telderi.

| # | Файл | URL | Что показать | Подпись для лота |
|---|------|-----|--------------|------------------|
| 1 | `01-landing-app.png` | https://reportagent.fileguardian.info/app#/ | Главная SPA после входа: навигация, зона загрузки файла | Личный кабинет — загрузка CSV/Excel |
| 2 | `02-report-formats.png` | https://reportagent.fileguardian.info/app#/preferences | Настройки: форматы PDF/Excel/PPTX, тема, email | Настройки форматов и брендинга |
| 3 | `03-pricing-stripe.png` | https://reportagent.fileguardian.info/app#/pricing | Страница тарифов Stripe | Подписки Stripe |
| 4 | `04-pricing-yookassa.png` | https://reportagent.fileguardian.info/app#/pricing-yookassa | Страница ЮKassa | Оплата через ЮKassa (РФ) |
| 5 | `05-voice.png` | https://reportagent.fileguardian.info/app#/voice | Страница голосового ввода | Голосовые задачи (Whisper + GPT) |
| 6 | `06-api-keys.png` | https://reportagent.fileguardian.info/app#/api-keys | Список API-ключей | REST API и ключи доступа |
| 7 | `07-swagger.png` | https://reportagent.fileguardian.info/docs | Swagger UI, блок `generate_report` | OpenAPI / Swagger документация |
| 8 | `08-help-docs.png` | https://reportagent.fileguardian.info/help/ | Главная MkDocs, переключатель RU | Пользовательская документация RU/EN |
| 9 | `09-report-result.png` | *после генерации* | История отчётов или скачанный PDF (превью) | Пример готового PDF-отчёта |
| 10 | `10-subscription.png` | https://reportagent.fileguardian.info/app#/subscription | Страница подписки / usage | Учёт лимитов и подписка |

**Совет:** для скрина №9 залогиньтесь как `telderi-demo@...`, загрузите `app/samples/sample_sales.csv`, дождитесь PDF и сделайте скрин превью или первой страницы PDF.

---

## Блок «Доступ к демо» (поле Telderi)

```
Демо: https://reportagent.fileguardian.info/app#/
Логин: telderi-demo@fileguardian.info
Пароль: [ВСТАВИТЬ ПАРОЛЬ ПОСЛЕ setup_telderi_demo.py]

Документация: https://reportagent.fileguardian.info/help/
API: https://reportagent.fileguardian.info/docs

Продаётся только исходный код. Домен и хостинг не входят в сделку.
```

---

## DNS-верификация Telderi

TXT-запись на **корне** `fileguardian.info`:

- Имя: `telderi-verification` (или как указано в кабинете Telderi)
- Значение: код из личного кабинета Telderi

Поддомен `reportagent` для верификации не используется.

---

## Чеклист перед публикацией

- [ ] Запустить `setup_telderi_demo.py` на VPS, сохранить пароль
- [ ] Сделать 8–10 скриншотов по таблице выше
- [ ] Вставить заголовок, краткое и полное описание
- [ ] Указать демо-логин/пароль в поле доступа
- [ ] Проверить TXT `telderi-verification` на `fileguardian.info`
- [ ] Установить цену 250 000 ₽ / блиц 420 000 ₽ / 7 дней
