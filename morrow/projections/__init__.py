"""Rebuildable read-side projections derived from the immutable event ledger.

Projections are never the source of truth. They can be deleted and rebuilt by
deterministic replay.

TODO(#6): current_child_state, active_investigations, active_hypotheses,
pending_approvals, active_learnings; plus delete-and-rebuild support.
"""
