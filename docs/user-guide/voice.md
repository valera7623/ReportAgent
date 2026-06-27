# Голосовой ввод

Голосовой запрос: аудио → Whisper (транскрипция) → GPT-4o-mini (intent) → отчёт или уточняющий вопрос.

## Требования

| Переменная | Описание |
|------------|----------|
| `OPENAI_API_KEY` | **Обязателен** (Whisper + LLM) |
| `OPENAI_BASE_URL` | ProxyAPI: `https://api.proxyapi.ru/openai/v1` |
| `VOICE_ENABLED` | `true` / `false` |
| `MAX_AUDIO_SIZE_MB` | Лимит размера (по умолчанию 25) |

Без `OPENAI_API_KEY` эндпоинты `/voice/*` возвращают **501 Not Implemented**.

## Поддерживаемые форматы

`mp3`, `wav`, `m4a`, `ogg` — до `MAX_AUDIO_SIZE_MB` МБ.

## Отправка голосового запроса

```bash
curl -X POST https://ваш-домен/voice/generate_report \
  -H "X-API-Key: $API_KEY" \
  -F "audio=@recording.m4a" \
  -F "email=user@example.com"
```

Ответ `202`:

```json
{
  "task_id": "abc-123",
  "status": "queued",
  "transcript": "Создай отчёт по Google Sheets ...",
  "intent": { "source_type": "sheets_url", "chart_type": "pie" },
  "download_url": "/tasks/abc-123/pdf"
}
```

## Уточняющие вопросы

Если данных недостаточно — `status: "needs_clarification"`:

```bash
curl -X POST https://ваш-домен/voice/clarify \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"task_id": "voice-abc...", "answer": "используй колонку revenue"}'
```

| Ситуация | Пример вопроса |
|----------|----------------|
| Не распознана речь | Повторите запрос чётче |
| Нет источника данных | Укажите ссылку на Google Sheets |
| Запрошен файл голосом | Предложите Sheets URL или загрузку файла |

## Распознавание формата

Из речи определяется формат отчёта: «сделай в Excel» → `excel`, «отправь в Notion» → `notion`.

## Тест

```bash
python3 scripts/test_voice.py \
  --base-url https://ваш-домен \
  --api-key "$API_KEY" \
  --audio /path/to/recording.wav
```

!!! warning "Два разных ключа"
    **ReportAgent API key** — заголовок `X-API-Key`. **OpenAI key** — только в `.env` на сервере.

## API

[API голоса](../api/voice.md)
