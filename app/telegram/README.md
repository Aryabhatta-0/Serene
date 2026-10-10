# app/telegram

Serene-side boundary for the Telegram surface. Hermes (the runtime) owns the
Telegram bot, scheduling and message transport; this directory holds the
Serene-owned tool/adapter contracts that Hermes calls into.

Nothing is implemented yet.

- Observation ingestion (raw -> structured, never overwriting raw evidence): #9
- Micro-question + approval UX (YES/NO/UNSURE, APPROVE/REJECT): #40

Authority note: Telegram input is untrusted. It produces observations; it never
directly mutates belief, memory or authorization state.
