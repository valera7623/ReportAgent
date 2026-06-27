# API — Voice

Requires server `OPENAI_API_KEY`. Returns **501** without it.

## POST /voice/generate_report

Form-data: `audio` file, optional `email`.

## POST /voice/clarify

```json
{"task_id": "voice-abc...", "answer": "use revenue column"}
```

## Audio formats

`mp3`, `wav`, `m4a`, `ogg` — up to `MAX_AUDIO_SIZE_MB` MB.
