# Contract: Telegram Bot API webhook

Adapter: `src/lead_capture/adapters/channels/telegram/` (research R17). Webhook path:
`POST /webhooks/telegram`.

## Inbound

Every request must carry `X-Telegram-Bot-Api-Secret-Token: <TELEGRAM_WEBHOOK_SECRET>`;
otherwise **401**. Body: one `Update` object.

| Update | Becomes `InboundMessage` |
|---|---|
| `message` with `text` (private chat) | `type=text`, `text`; `/start <id>` also sets `referral_source=<id>` |
| `message` with `contact` | `type=contact`, `shared_phone=<contact.phone_number>` |
| `message` with anything else (voice, photo, sticker…) | `type=unsupported` |
| `callback_query` (inline button tap) | `type=interactive`, `choice_id=<data>` |
| any update from a group/channel chat, edited messages, others | ignored |

Common fields: `id = "tg-<update_id>"` (dedupe), `contact = "tg:<chat.id>"`,
`profile_name = from.first_name`, `timestamp = date` (UTC).

## Outbound

`POST {api_base_url}/bot<TOKEN>/sendMessage` with `chat_id`, `text` and one of:

| Reply | `reply_markup` |
|---|---|
| tap options (all IDs ≤ 64 bytes) | `inline_keyboard`, `buttons_per_row` per row, `callback_data` = choice ID |
| phone number requested (FR-032) | one-time `keyboard` with a `request_contact` button labelled from `config/messages.yaml` |
| plain text | `remove_keyboard: true` |

Pending button taps for the chat are acknowledged first with `answerCallbackQuery`.
Retries: 429/5xx and network errors, up to `channel.max_retries` with backoff; other 4xx
(e.g. 403 = the user blocked the bot) are not retried → `ChannelError`.
`SentMessage.id = "tg-out-<chat id>-<message_id>"`.

## Registration

`lead-capture set-webhook https://<public-host>` → `setWebhook(url=<host>/webhooks/telegram,
secret_token, allowed_updates=[message, callback_query])`.
