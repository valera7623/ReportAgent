# Voice Input

Voice flow: audio → Whisper (transcription) → GPT-4o-mini (intent) → report or clarification.

## Requirements

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Required (Whisper + LLM) |
| `OPENAI_BASE_URL` | ProxyAPI: `https://api.proxyapi.ru/openai/v1` |
| `VOICE_ENABLED` | `true` / `false` |

Without `OPENAI_API_KEY`, `/voice/*` returns **501 Not Implemented**.

## Supported formats

`mp3`, `wav`, `m4a`, `ogg` — up to `MAX_AUDIO_SIZE_MB` MB.

## Send voice request

```bash
curl -X POST https://your-domain/voice/generate_report \
  -H "X-API-Key: $API_KEY" \
  -F "audio=@recording.m4a"
```

## Clarification

```bash
curl -X POST https://your-domain/voice/clarify \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"task_id": "voice-abc...", "answer": "use revenue column"}'
```

## Test

```bash
python3 scripts/test_voice.py --base-url https://your-domain --api-key "$API_KEY" --audio recording.wav
```

## API

[Voice API](../api/voice.md)
