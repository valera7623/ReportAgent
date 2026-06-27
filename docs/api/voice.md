# API — Голос

Требует `OPENAI_API_KEY` на сервере. Без него — **501**.

## POST /voice/generate_report

Form-data: `audio` (файл), опционально `email`.

```bash
curl -X POST https://ваш-домен/voice/generate_report \
  -H "X-API-Key: $API_KEY" \
  -F "audio=@recording.m4a"
```

**Ответ 202:**

```json
{
  "task_id": "abc-123",
  "status": "queued",
  "transcript": "Создай отчёт...",
  "intent": {"source_type": "sheets_url", "chart_type": "pie"},
  "download_url": "/tasks/abc-123/pdf"
}
```

При недостатке данных: `"status": "needs_clarification"`.

## POST /voice/clarify

```json
{"task_id": "voice-abc...", "answer": "используй колонку revenue"}
```

## GET /tasks/{task_id}

При `NEEDS_CLARIFICATION` — поля `clarification_question`, `partial_intent`.

## Форматы аудио

`mp3`, `wav`, `m4a`, `ogg` — до `MAX_AUDIO_SIZE_MB` МБ.
