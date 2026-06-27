# Глоссарий

| Термин | Описание |
|--------|----------|
| **API-ключ** | Токен `ra_...` для аутентификации запросов (`X-API-Key`) |
| **Агент** | Модуль pipeline: parser, analyst, visualizer и др. |
| **Celery** | Очередь фоновых задач (генерация отчётов) |
| **Intent** | Распознанный смысл голосового запроса (источник, формат, график) |
| **JWT** | JSON Web Token для временного доступа после login |
| **Preview** | Предпросмотр данных до полной генерации (Redis, 1 ч) |
| **Self-healing** | Автовосстановление агентов через ChromaDB RAG |
| **Task ID** | UUID Celery-задачи; используется для статуса и скачивания |
| **Webhook** | HTTP POST уведомление на ваш URL при готовности отчёта |
| **Freemium** | Бесплатный тариф с лимитом 5 отчётов/месяц |

## Сокращения

| Сокр. | Расшифровка |
|-------|-------------|
| PPTX | PowerPoint Open XML |
| RAG | Retrieval-Augmented Generation |
| SMTP | Simple Mail Transfer Protocol |
| VPS | Virtual Private Server |
