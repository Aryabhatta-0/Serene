"""Safe N-of-1 experiment lifecycle (issues #24, #25, #26).

`lifecycle` holds pure step functions over `KernelState` + `now` that return
`EventDraft`s (the timer seam a runtime scheduler calls: `nudge_due`,
`timeout_due`, `start_due`, `learning_validity_due`); `service` appends them
through the ledger, whose admission recomputes every decision.
"""
