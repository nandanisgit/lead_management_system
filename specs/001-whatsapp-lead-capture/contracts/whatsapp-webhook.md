# Contract: WhatsApp Webhook and Outbound Messages

The service exposes one public HTTPS endpoint to Meta's WhatsApp Cloud API and
sends messages through the Cloud API's messages endpoint.

## Inbound

### `GET /webhooks/whatsapp` — subscription verification

| Query param | Expected |
|---|---|
| `hub.mode` | `subscribe` |
| `hub.verify_token` | equals `WA_VERIFY_TOKEN` |
| `hub.challenge` | any string |

- Match → `200`, body = `hub.challenge` (plain text).
- Otherwise → `403`.

### `POST /webhooks/whatsapp` — events

(Mounted as `/webhooks/{channel}` with `channel = whatsapp`; another channel adapter gets its own path.)

- **Header** `X-Hub-Signature-256: sha256=<hex>` = HMAC-SHA256 of the raw body
  with `WA_APP_SECRET`. Missing or wrong → `401`, nothing stored.
- **Response**: `200` within 1 second for every well-signed payload, including
  ones that are ignored or duplicates. Processing happens after the response.
- **Handled payload items** (under `entry[].changes[].value`):

| Item | Action |
|---|---|
| `messages[]` type `text` | store (dedupe on `id`), schedule a turn for `from` |
| `messages[]` type `interactive` (`button_reply` / `list_reply`) | store the reply ID and title as text, schedule a turn |
| `messages[]` types `audio`, `image`, `video`, `document`, `sticker`, `location`, `contacts` | store as `unsupported`, schedule a turn (bot asks for text — FR-028) |
| `messages[].referral` | record `source_id` as the conversation's `source` |
| `contacts[].profile.name` | update `Contact.wa_profile_name` |
| message echoes (sent by a human from the Business app) | store as `direction = echo`; never trigger a bot turn |
| `statuses[]` | ignored in v1 (optionally logged by ID) |
| anything else | ignored |

- **Idempotency**: a second delivery of the same message `id` is acknowledged
  and dropped (unique constraint on `wa_message_id`).

### `GET /healthz`

`200 {"status":"ok","db":"ok","outbox_pending":<int>}` — no personal data.

## Outbound (bot → WhatsApp)

This contract is implemented by the `WhatsAppCloudChannel` adapter of the
generic `MessagingChannel` interface (research R16). The engine never calls
these methods by WhatsApp name; it sends normalised `OutboundMessage`s and
checks `capabilities`. The WhatsApp-specific mapping is:

| Method | Used for | Window rule |
|---|---|---|
| `send_text(to, body)` | normal replies | only if `last_inbound_at` < 24 h ago |
| `send_choices(to, body, choices)` → reply buttons when ≤ 3 choices | consent (Yes / No), mode (Online / Home / Either), summary (Confirm / Change) | only inside 24 h |
| `send_choices(to, body, choices)` → interactive list when 4–10 choices | board choice | only inside 24 h |

- **No templates, no business-initiated messages (FR-022).** Every send is a reply to the tutee.
- **Window guard**: before every send, the engine checks `last_inbound_at` against `capabilities.window_hours`. Outside the window the send is dropped and logged as `send_outside_window` (IDs only). A tutee's new message reopens the window.
- Button and row titles in the tutee's language (`en` / `hi`).
- Every successful send stores an outbound `Message` with the returned ID.
- Failures: retry up to `channel.max_retries` times with backoff on 429/5xx; on permanent failure
  log the error class and conversation ID only.

## Configuration

| Variable | Purpose |
|---|---|
| `WA_PHONE_NUMBER_ID` | sender phone number ID |
| `WA_ACCESS_TOKEN` | system-user access token |
| `WA_APP_SECRET` | signature verification |
| `WA_VERIFY_TOKEN` | subscription verification |
| `WA_API_VERSION` | Graph API version, e.g. `v23.0` |
