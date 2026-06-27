# Начало работы

Руководство для пользователей ReportAgent — аналитиков, менеджеров и интеграторов.

## Зачем нужен ReportAgent

ReportAgent превращает табличные данные в готовые отчёты с графиками:

- загрузите CSV/Excel или укажите Google Sheets;
- получите PDF, Excel, презентацию или страницу в Notion;
- настройте тип графиков, тему и email по умолчанию;
- автоматизируйте через API и webhooks.

## Регистрация

1. Откройте веб-интерфейс: `https://ваш-домен/app#/register`
2. Введите **email** и **пароль** (минимум 8 символов).
3. Подтвердите email по ссылке из письма (`/app#/verify`).
4. Войдите на `/app#/login`.
5. Создайте **первый API-ключ** — он понадобится для API и интеграций.

!!! tip "SMTP обязателен для регистрации"
    Администратор должен настроить `SMTP_*` и `FRONTEND_URL` в `.env`, иначе письма подтверждения не отправятся.

### Регистрация через API

```bash
curl -X POST https://ваш-домен/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "securepass123",
    "password_confirm": "securepass123"
  }'
```

## Вход

### Email + пароль (веб)

1. `/app#/login` → вкладка **Email**
2. После входа получите JWT (15 мин) для создания API-ключа

### API-ключ (постоянный доступ)

1. `/app#/login` → вкладка **API-ключ**
2. Вставьте ключ формата `ra_...`
3. Все защищённые запросы отправляйте с заголовком:

```http
X-API-Key: ra_ваш_ключ
```

## Первый API-ключ

После входа по JWT:

```bash
curl -X POST https://ваш-домен/api/keys/generate \
  -H "Authorization: Bearer eyJ..." \
  -H "Content-Type: application/json" \
  -d '{"name": "Default"}'
```

!!! warning "Ключ показывается один раз"
    Сохраните полный ключ сразу. В списке ключей виден только префикс (`ra_abc12`).

## Веб-интерфейс

После входа доступны разделы:

| Раздел | URL | Назначение |
|--------|-----|------------|
| **Дашборд** | `/app#/dashboard` | Статистика, новый отчёт |
| **Отчёты** | `/app#/reports` | История генераций |
| **Ключи** | `/app#/keys` | Управление API-ключами |
| **Настройки** | `/app#/preferences` | Графики, тема, формат |
| **Webhooks** | `/app#/webhooks` | URL уведомлений |
| **Тарифы** | `/app#/pricing` | Подписка |

## Быстрый тест

```bash
# 1. Сгенерировать отчёт
TASK_ID=$(curl -s -X POST https://ваш-домен/generate_report \
  -H "X-API-Key: $API_KEY" \
  -F "file=@samples/sample_sales.csv" | jq -r .task_id)

# 2. Скачать PDF (~10 сек)
curl -OJ -H "X-API-Key: $API_KEY" \
  "https://ваш-домен/tasks/${TASK_ID}/pdf"
```

## Что дальше

- [Создание отчётов](reports.md)
- [Превью перед отправкой](preview.md)
- [API-ключи и аутентификация](../api/auth.md)
