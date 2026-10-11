"""Hermes adapters. Only code under `serene.adapters.hermes` may import Hermes.

Serene reaches Hermes over its OpenAI-compatible API server (no in-process
import), so the kernel and its tests run without Hermes installed.
"""

from serene.adapters.hermes.runtime import (
    HermesAgentRuntime,
    HermesNotConfigured,
    PlannerUnavailable,
    TokenPricing,
    render_context,
)
from serene.adapters.hermes.scripted import ScriptedHermesTransport, wire_response
from serene.adapters.hermes.transport import (
    HermesRequest,
    HermesResponse,
    HermesToolCall,
    HermesTransport,
    HermesTransportError,
    HermesUsage,
    HttpHermesTransport,
    parse_responses_payload,
    transport_from_env,
)

__all__ = [
    "HermesAgentRuntime",
    "HermesNotConfigured",
    "HermesRequest",
    "HermesResponse",
    "HermesToolCall",
    "HermesTransport",
    "HermesTransportError",
    "HermesUsage",
    "HttpHermesTransport",
    "PlannerUnavailable",
    "ScriptedHermesTransport",
    "TokenPricing",
    "parse_responses_payload",
    "render_context",
    "transport_from_env",
    "wire_response",
]
