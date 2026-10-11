"""Web app channel adapter: parent decisions made in the Serene web app (issue #37).

The web app is an authenticated channel (`SourceKind.WEB_APP`). This adapter is
the Serene-side boundary that mints the `ChannelReceipt` for a decision an
already-authenticated parent made, and hands it to the ledger, whose admission
recomputes every authority rule. It never decides anything itself.
"""

from serene.adapters.web.approvals import (
    WebApprovalChannel,
    WebApprovalCommand,
    WebDecision,
    WebDecisionResult,
)

__all__ = ["WebApprovalChannel", "WebApprovalCommand", "WebDecision", "WebDecisionResult"]
