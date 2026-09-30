# Quickstart: WhatsApp Lead Capture

How to set up, run and validate the feature end-to-end. Commands assume the
layout in [plan.md](plan.md); they become runnable once the Build stage creates
the code.

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Docker (for production-like runs)
- An Anthropic API key — or, for the first days, [Ollama](https://ollama.com) (free, see below)
- A Meta app with WhatsApp Cloud API: phone number ID, access token, app secret, a verify token of your choice; coexistence enabled on the business number (see [research.md R4](research.md))
- For Telegram instead of (or as well as) WhatsApp: a bot token from @BotFather (see "Telegram" below)
- A native Google Sheet with tabs `Leads`, `Handoffs`, `Lists` and headers exactly as in [contracts/lead-sheet.md](contracts/lead-sheet.md), shared as **Editor** with a service-account email
- For live webhook tests from a laptop: a tunnel such as `cloudflared` or `ngrok`

## Setup

```bash
uv sync                      # install dependencies
cp .env.example .env         # fill in the variables below
uv run alembic upgrade head  # create the local SQLite store
uv run lead-capture check-sheet   # verifies access and header contract
uv run lead-capture sync-lists    # writes the allowed values from config/requirement.yaml into the Lists tab
```

| Variable | Notes |
|---|---|
| `ANTHROPIC_API_KEY`, `LLM_MODEL` | default `claude-sonnet-5-5` |
| `EVAL_TUTEE_MODEL` | model that plays the tutee in evals and load tests, e.g. `claude-haiku-4-5` |
| `LOAD_TEST_SHEET_ID` | a separate **test** Google Sheet for the `burst` load profile (never the real one) |
| `WA_PHONE_NUMBER_ID`, `WA_ACCESS_TOKEN`, `WA_APP_SECRET`, `WA_VERIFY_TOKEN`, `WA_API_VERSION` | see [contracts/whatsapp-webhook.md](contracts/whatsapp-webhook.md) |
| `LEAD_SHEET_ID`, `GOOGLE_SERVICE_ACCOUNT_FILE` | service-account JSON path (never committed) |
| `DATABASE_URL` | default `sqlite:///data/lead_capture.db` |
| `TZ_NAME` | `Asia/Kolkata` |

## Free local model (Ollama) for the first days

`config/settings.yaml` ships with `llm.provider: ollama`, so no API key or model cost is needed:

```bash
brew install ollama          # or download from ollama.com
ollama serve                 # leave running (the Mac app starts it automatically)
ollama pull gemma3:12b       # the bot's model (llm.ollama.extraction_model / reply_model)
ollama pull gemma3:4b        # the simulated tutee for evals (evals.ollama_tutee_model)
uv run lead-capture chat --number +919999900001
uv run lead-capture eval --provider ollama --scenario hinglish_home_dwarka
```

Slow machine: set both models to `gemma3:4b` (or `LC__LLM__OLLAMA__REPLY_MODEL=gemma3:4b`).
The first message after a pause is slow while the model loads.

**Switch to Claude** (before going live): set `llm.provider: anthropic` in
`config/settings.yaml` (or `LC__LLM__PROVIDER=anthropic`) and put `ANTHROPIC_API_KEY` in
`.env`. Run the full eval suite on Claude before production — Ollama results don't count
toward the release gate.

## Automated validation

```bash
uv run pytest                          # unit + contract + integration (fakes, no network)
uv run lead-capture eval               # full eval suite against the real model
uv run lead-capture eval --scenario hinglish_home_dwarka   # one scenario
```

Expected: all tests pass; every eval check at ≥ 95% pass rate (see
[research.md R10](research.md)). In each eval a simulated tutee answers only
from the scenario's `tutee_facts`, and the recorded lead is compared with those
facts. The eval report is written to `evals/reports/<timestamp>.md`.

## Load testing (before each release)

```bash
uv run lead-capture load --profile capacity   # stubbed model: webhook + infra capacity
uv run lead-capture load --profile burst      # real model + test sheet: 30 tutees at once
uv run lead-capture load --profile soak       # stubbed model: 3 hours steady traffic
```

Pass criteria per profile are in [research.md R13](research.md); for `burst`:
reply p95 < 5 s, every confirmed lead in the test sheet exactly once within
10 s, outbox back to 0. Reports go to `load/reports/<timestamp>.md`. The
`burst` profile makes real Claude calls, so it uses API credits.

## Local conversation without WhatsApp

```bash
uv run lead-capture chat --number +919999900001
```

Starts a terminal chat with the real conversation engine, a fake WhatsApp
sender and (by default) the in-memory lead repository. Add `--sheet` to write
to the real Google Sheet.

## Telegram (second channel, research R17)

No business verification, no cost. One-time setup:

1. In Telegram, open **@BotFather**, send `/newbot`, choose a name and a username ending in
   `bot`. Copy the token it gives you.
2. In `.env` (never in code or chat):
   ```bash
   TELEGRAM_BOT_TOKEN=123456:ABC...
   TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 16)   # paste the generated value
   ```
3. Run the service on Telegram and expose it:
   ```bash
   LC__CHANNEL__PROVIDER=telegram uv run uvicorn lead_capture.app:app --port 8000
   cloudflared tunnel --url http://localhost:8000
   ```
4. Register the webhook (repeat whenever the tunnel URL changes):
   ```bash
   LC__CHANNEL__PROVIDER=telegram uv run lead-capture set-webhook https://<tunnel>.trycloudflare.com
   ```
5. Open `t.me/<your_bot_username>` on your phone and press **Start**.

The bot asks for a phone number after consent (FR-032) with a **Share my phone number**
button; typing a number works too. To make Telegram the default, set
`channel.provider: telegram` in `config/settings.yaml`.

## Live end-to-end check

```bash
uv run uvicorn lead_capture.app:app --port 8000
cloudflared tunnel --url http://localhost:8000     # or ngrok http 8000
```

Set the tunnel URL + `/webhooks/whatsapp` as the callback in the Meta app with
your verify token, then message the business number from a test phone.

## Validation scenarios

| # | Spec | Do this | Expect |
|---|---|---|---|
| 1 | US1 | Say "Hi need maths tutor for my son", consent, answer questions, confirm | ≤ 2 questions per message; summary; one `NEW` row in `Leads` within 10 s; closing message matches the time of day |
| 2 | US1 | Send "Class 9 CBSE maths and science, home tuition in Dwarka, weekday evenings" as the first detail | Only missing fields are asked for |
| 3 | US1 | Say "not sure" when asked about budget | Bot asks for an approximate figure; never suggests an amount |
| 4 | US2 | Stop halfway; reply again later | Bot recaps and continues; no row until confirmation |
| 5 | US2 | After confirming, say "also need a tutor for my daughter" | A second, separate lead |
| 6 | US3 | Ask for home tuition in Pune, then decline online | No row; conversation closed `out_of_area` |
| 7 | US3 | Write in Tamil | Polite English + Hindi message about supported languages |
| 8 | US4 | Say "can I talk to someone?" | Handover message; row in `Handoffs`; bot silent afterwards |
| 9 | US5 | Reply "No" to consent | Nothing stored except the refusal; conversation closed |
| 10 | US5 | Say "please delete my data" | Leads and conversations removed; confirmation sent |
| 11 | Edge | Send a voice note | Bot asks for a text reply |
| 12 | Edge | Replay a webhook payload twice (`uv run lead-capture replay <file>`) | One message stored, one reply, no duplicate row |
| 13 | Edge | Revoke the sheet share, confirm a lead, restore the share | Tutee still gets confirmation; row appears after restore; `/healthz` shows `outbox_pending` returning to 0 |

## Deploy

```bash
docker build -t lead-capture .
docker run -d --env-file .env -v lead_data:/app/data -p 8000:8000 lead-capture
```

Put it behind HTTPS (Caddy or the host's reverse proxy) and point the Meta
webhook at `https://<host>/webhooks/whatsapp`.
