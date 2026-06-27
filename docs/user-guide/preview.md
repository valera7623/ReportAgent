# Превью перед отправкой

Перед генерацией полного отчёта можно просмотреть **превью**: таблица (первые 50 строк), базовая статистика и графики.

## Поток

1. `POST /api/reports/preview` — загрузка файла или Google Sheets URL
2. Ответ: `preview_id`, `data` (headers, rows, summary, charts), `expires_at`
3. Графики: `GET /api/preview/chart/{preview_id}/{chart_index}` (PNG)
4. Смена типа графика: `POST /api/reports/preview/regenerate-chart`
5. Подтверждение: `POST /api/reports/preview/confirm` → полная генерация

!!! note "Срок хранения"
    Превью хранится в Redis **1 час** и **не** попадает в историю до подтверждения.

## Через API

```bash
# Создать превью
curl -X POST https://ваш-домен/api/reports/preview \
  -H "X-API-Key: $API_KEY" \
  -F "file=@sample_sales.csv"

# Подтвердить и сгенерировать PDF
curl -X POST https://ваш-домен/api/reports/preview/confirm \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"preview_id":"uuid","output_format":"pdf"}'
```

## Большие файлы (> 10 MB)

Обрабатываются асинхронно через Celery. Опрашивайте:

```bash
GET /api/reports/preview/status/{job_id}
```

## Веб-интерфейс

На **Дашборде** — блок «Новый отчёт» с модальным превью: таблица, графики, кнопка «Подтвердить».

## Тест

```bash
python3 scripts/test_preview.py --base-url http://localhost:8000
```

## API

Подробнее: [API превью](../api/preview.md)
