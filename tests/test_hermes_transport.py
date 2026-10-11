"""Hermes transport: Responses-API parsing and fail-closed configuration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from serene.adapters.hermes import (
    HermesTransportError,
    HttpHermesTransport,
    parse_responses_payload,
    transport_from_env,
)


def _payload(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": "resp_1",
        "status": "completed",
        "model": "hermes-agent",
        "runtime": {"provider": "anthropic", "model": "claude-opus-5-5"},
        "output": [
            {
                "type": "function_call",
                "call_id": "c1",
                "name": "browser_navigate",
                "arguments": '{"url": "https://example.org/policy"}',
            },
            {"type": "function_call_output", "call_id": "c1", "output": "Pickup policy text"},
            {
                "type": "message",
                "phase": "commentary",
                "content": [{"type": "output_text", "text": "thinking aloud"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "{}"}],
            },
        ],
        "usage": {"input_tokens": 50, "output_tokens": 20, "total_tokens": 70},
    }
    base.update(overrides)
    return base


def test_executed_tool_calls_and_final_text_are_parsed() -> None:
    response = parse_responses_payload(_payload())
    assert response.output_text == "{}"  # commentary is never part of the answer
    (call,) = response.tool_calls
    assert call.name == "browser_navigate" and call.output == "Pickup policy text"
    assert call.parsed_arguments() == {"url": "https://example.org/policy"}
    assert response.usage.input_tokens == 50 and response.model == "claude-opus-5-5"


def test_missing_usage_is_unknown_not_zero() -> None:
    response = parse_responses_payload(_payload(usage=None))
    assert response.usage.input_tokens is None and response.usage.output_tokens is None


@pytest.mark.parametrize(
    ("payload", "kind"),
    [
        ({"status": "failed", "output": []}, "TRANSIENT"),
        ({"status": "incomplete", "output": []}, "PROTOCOL"),
        ({"output": "nope"}, "PROTOCOL"),
        (
            {"output": [{"type": "message", "content": [{"type": "refusal", "refusal": "no"}]}]},
            "REFUSED",
        ),
    ],
)
def test_failures_are_classified(payload: dict[str, Any], kind: str) -> None:
    with pytest.raises(HermesTransportError) as exc:
        parse_responses_payload(payload)
    assert exc.value.kind == kind


def test_http_transport_refuses_plaintext_remote_hosts_and_missing_keys() -> None:
    with pytest.raises(ValueError):
        HttpHermesTransport("http://hermes.internal:8642/v1", "k")
    with pytest.raises(ValueError):
        HttpHermesTransport("http://127.0.0.1:8642/v1", "")
    assert HttpHermesTransport("https://hermes.example.org/v1", "k")


def test_unconfigured_environment_yields_no_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_API_SERVER_KEY", raising=False)
    assert transport_from_env() is None


def test_installed_hermes_responses_shape_is_parsed() -> None:
    """Shape of hermes-agent v0.21.6 `/v1/responses` (gateway/platforms/
    api_server_openai_routes.py `_extract_output_items`): reasoning items, completed
    function_call / function_call_output replays, then one final message."""
    payload = {
        "id": "resp_abc",
        "object": "response",
        "status": "completed",
        "model": "hermes-agent",
        "output": [
            {"type": "reasoning", "summary": [{"type": "summary_text", "text": "plan"}]},
            {
                "id": "fc_1",
                "type": "function_call",
                "status": "completed",
                "name": "web_extract",
                "arguments": '{"urls": ["https://example.org/policy"]}',
                "call_id": "call_1",
            },
            {
                "id": "fco_1",
                "type": "function_call_output",
                "status": "completed",
                "call_id": "call_1",
                "output": "Pickup 15:00-17:30",
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": '{"contract": "x"}'}],
            },
        ],
        "usage": {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
    }
    response = parse_responses_payload(payload)
    assert response.output_text == '{"contract": "x"}'  # reasoning never leaks into the answer
    (call,) = response.tool_calls
    assert (call.name, call.output) == ("web_extract", "Pickup 15:00-17:30")
    assert response.usage.output_tokens == 3


# --------------------------------------------------------------- provider-failure envelopes
_FIXTURES = Path(__file__).parent / "fixtures"
_WARN = "\u26a0\ufe0f"  # WARNING SIGN + VS16, as Hermes renders it


def _envelope(text: str, usage: dict[str, int] | None = None) -> dict[str, Any]:
    return {
        "id": "resp_x",
        "object": "response",
        "status": "completed",
        "model": "hermes-agent",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            }
        ],
        "usage": usage or {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
    }


def test_captured_provider_auth_envelope_is_an_auth_failure_not_model_output() -> None:
    """Captured from the live hermes-agent v0.21.6 API server with no provider
    credentials (2026-10-10): HTTP 200, status "completed", zero usage."""
    payload = json.loads((_FIXTURES / "hermes_provider_auth_failure.json").read_text("utf-8"))
    with pytest.raises(HermesTransportError) as exc:
        parse_responses_payload(payload)
    assert (exc.value.kind, exc.value.code) == ("AUTH", "PROVIDER_AUTH")


@pytest.mark.parametrize(
    ("text", "kind", "code"),
    [
        (f"{_WARN} Provider rate-limited: 429 Too Many", "TRANSIENT", "PROVIDER_RATE_LIMITED"),
        (f"{_WARN} Provider error: Connection refused", "TRANSIENT", "PROVIDER_UNREACHABLE"),
        (f"{_WARN} Something unexpected happened", "PROTOCOL", "PROVIDER_FAILURE"),
    ],
)
def test_provider_failure_envelopes_are_classified(text: str, kind: str, code: str) -> None:
    with pytest.raises(HermesTransportError) as exc:
        parse_responses_payload(_envelope(text))
    assert (exc.value.kind, exc.value.code) == (kind, code)


def test_model_text_with_a_warning_sign_is_still_model_output() -> None:
    payload = _envelope(f"{_WARN} careful", usage={"input_tokens": 12, "output_tokens": 3})
    assert parse_responses_payload(payload).output_text == f"{_WARN} careful"
