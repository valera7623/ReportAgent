# API — Webhooks

Outgoing POST notifications on report completion or failure.

## Events

| Event | When |
|-------|------|
| `report.completed` | Report generated successfully |
| `report.failed` | Pipeline error |

## POST /api/webhooks/register

Register callback URL with optional HMAC secret.

## Payload

Includes `event`, `task_id`, `download_url`, `output_format`, `timestamp`.

## HMAC signature

Header `X-Webhook-Signature` = HMAC-SHA256(secret, canonical JSON).

## Admin

`GET /admin/webhooks/stats`
