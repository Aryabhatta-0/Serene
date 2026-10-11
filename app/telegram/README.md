# app/telegram

Serene-side boundary for the Telegram surface (branch A). Hermes owns the bot
transport, scheduling and model routing; Serene owns what an update *means*.

| Piece | Where |
| --- | --- |
| Authenticated ingress (webhook secret, bindings, receipts) | `serene/adapters/telegram/channel.py` |
| Exact one-time prompts (APPROVE/REJECT, YES/NO/UNSURE) | `serene/adapters/telegram/prompts.py` |
| WSGI endpoint | `serene/adapters/telegram/wsgi.py` |
| Runnable server | `app/telegram/webhook_server.py` |

```bash
uv run python app/telegram/webhook_server.py --port 8787
```

The server refuses to start without `SUPABASE_DB_URL`, `TELEGRAM_WEBHOOK_SECRET`,
`SERENE_TELEGRAM_BINDINGS` and a Hermes API server key.

## What an update can do

| Update | Result |
| --- | --- |
| Missing/wrong `X-Telegram-Bot-Api-Secret-Token` | 401, nothing read or recorded |
| Sender not bound, group chat, bot | ignored; Telegram ids never reach the ledger |
| Text message | `OBSERVATION_REPORTED` (byte-faithful, channel-authenticated) then a separate `OBSERVATION_STRUCTURED` or `OBSERVATION_STRUCTURING_FAILED` |
| Tap on an approval button | `APPROVAL_GRANTED` / `APPROVAL_REJECTED` with a `ChannelReceipt` — only if token, user, chat, message and shown intervention digest all match, once |
| Tap on a micro-question button | one `OBSERVATION_REPORTED` answering that `EVIDENCE_REQUESTED` (`YES`/`NO`/`UNSURE`) |

Typed text such as "approve" is always just an observation (#40). The kernel
re-checks every decision anyway (approver, expiry, digest, single use).

## Hermes wiring (manual; Hermes is not installed in CI)

Either register this endpoint as the bot's webhook (`setWebhook` with the same
secret token; Hermes then must not poll the same bot), or run Hermes in
polling mode with a relay that forwards each raw Update to this endpoint with
the secret header. The relay must forward updates verbatim; Serene computes
the evidence digest over the exact text it receives.
