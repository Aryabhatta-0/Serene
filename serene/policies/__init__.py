"""Deterministic policies: the code that decides, not the model.

Promotion Gate (epistemic ladder), GREEN/AMBER/RED safety classification,
parent approval lifecycle, experiment admission and evidence-acquisition
ordering. Every policy fails closed and returns machine-readable reasons.
"""

from serene.policies.decision import PolicyDecision

__all__ = ["PolicyDecision"]
