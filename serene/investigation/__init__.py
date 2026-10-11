"""Investigation runtime (branch A): boundary, context, hypotheses, evidence need.

Model reasoning happens behind `AgentRuntime`; everything here is deterministic
orchestration over ledger state. Authority stays in the kernel: this package
only ever *proposes* events through `EventLedger.append_event`.
"""
