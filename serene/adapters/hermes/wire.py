"""Versioned wire contract between Serene and the Hermes model (structured output).

The model never sees or mints kernel identifiers for new objects: it refers to
new items with short local refs ("P1", "H2") and to existing ones only by ids
that were present in its rendered context. The adapter then mints ids,
attaches provenance and builds kernel entities; the kernel boundary admits.

Validation is staged and fails closed:
  1. byte bound and an optional single ```json fence (the only normalization);
  2. JSON with duplicate keys or non-finite numbers is rejected;
  3. strict schema (closed variants, bounded lengths, no extra fields,
     contract version must match exactly);
  4. semantic checks (ref resolution, visibility, evidence status) in the runtime.

The model-facing contract text is rendered from these models (`propose_contract`,
`plan_contract`), so every enum value and bound it states is the one validation
enforces. A rejection carries `WireError.issues`: field locations and validation
types built only from schema names and schema bounds, never from model text.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Annotated, Any, Final, Literal, TypeVar, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, ValidationError

from serene.domain.base import ShortText, Tag
from serene.domain.entities import Burden, InterventionCategory
from serene.domain.events import AcquisitionMode, PredictedAnswer

WIRE_VERSION: Final = "serene-hermes-wire/1"
MAX_WIRE_BYTES: Final = 64_000

LocalRef = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Za-z0-9]{0,7}$")]
KernelRef = Annotated[str, StringConstraints(pattern=r"^[a-z]{3}_[0-9a-f]{32}$")]
Ref = LocalRef | KernelRef
HttpsUrl = Annotated[str, StringConstraints(pattern=r"^https://[^\s]{1,2000}$")]


class _Wire(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class WireObservation(_Wire):
    kind: Literal["observation"]
    evidence_ids: tuple[KernelRef, ...] = Field(min_length=1, max_length=8)
    statement: ShortText
    contexts: tuple[Tag, ...] = Field(default=(), max_length=8)


class WirePattern(_Wire):
    kind: Literal["pattern"]
    ref: LocalRef
    observation_ids: tuple[KernelRef, ...] = Field(min_length=2, max_length=32)
    counter_observation_ids: tuple[KernelRef, ...] = Field(default=(), max_length=32)
    description: ShortText
    contexts: tuple[Tag, ...] = Field(default=(), max_length=8)


class WireHypothesis(_Wire):
    kind: Literal["hypothesis"]
    ref: LocalRef
    pattern_refs: tuple[Ref, ...] = Field(min_length=1, max_length=8)
    statement: ShortText
    supporting_evidence_ids: tuple[KernelRef, ...] = Field(default=(), max_length=32)
    counter_evidence_ids: tuple[KernelRef, ...] = Field(default=(), max_length=32)
    alternative_explanations: tuple[ShortText, ...] = Field(default=(), max_length=8)
    known_confounders: tuple[ShortText, ...] = Field(default=(), max_length=8)
    falsification_criteria: tuple[ShortText, ...] = Field(min_length=1, max_length=4)
    contexts: tuple[Tag, ...] = Field(min_length=1, max_length=8)
    supersedes: KernelRef | None = None


class WireExperiment(_Wire):
    kind: Literal["experiment"]
    hypothesis_ref: Ref
    category: InterventionCategory
    description: ShortText
    reversible: bool
    max_duration_days: int = Field(ge=1, le=365)
    burden: Burden
    comparison: ShortText
    outcome_measure: ShortText


class WireNeedEvidence(_Wire):
    kind: Literal["need_evidence"]
    requested_fields: tuple[Tag, ...] = Field(min_length=1, max_length=8)
    rationale: ShortText


class WireAbstain(_Wire):
    kind: Literal["abstain"]
    reason: ShortText


WireProposal = Annotated[
    WireObservation
    | WirePattern
    | WireHypothesis
    | WireExperiment
    | WireNeedEvidence
    | WireAbstain,
    Field(discriminator="kind"),
]


class WireProposals(_Wire):
    contract: Literal["serene-hermes-wire/1"]
    proposals: tuple[WireProposal, ...] = Field(max_length=16)


class WirePrediction(_Wire):
    hypothesis_id: KernelRef
    expected: PredictedAnswer


class WireCandidate(_Wire):
    candidate_id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9_\-]{1,64}$")]
    requested_fields: tuple[Tag, ...] = Field(min_length=1, max_length=8)
    acquisition_mode: AcquisitionMode
    rationale: ShortText
    question: ShortText | None = None
    subject: Tag | None = None
    allowed_domains: tuple[
        Annotated[str, StringConstraints(pattern=r"^[a-z0-9.\-]{1,253}$")], ...
    ] = Field(default=(), max_length=8)
    predictions: tuple[WirePrediction, ...] = Field(default=(), max_length=8)


class WirePlan(_Wire):
    contract: Literal["serene-hermes-wire/1"]
    candidates: tuple[WireCandidate, ...] = Field(max_length=8)


class WireCapture(_Wire):
    url: HttpsUrl
    subject: Tag
    effective_date: date
    fields: dict[Tag, ShortText] = Field(max_length=16)
    excerpt: Annotated[str, StringConstraints(min_length=1, max_length=2000)]


class WireBrowseReport(_Wire):
    contract: Literal["serene-hermes-wire/1"]
    captures: tuple[WireCapture, ...] = Field(max_length=4)


class WireError(ValueError):
    """Machine-readable parse/schema failure. Never echoes model text.

    `code` is a stable reason code (ledger/telemetry); `issues` are safe, bounded
    repair hints such as "proposals[4].experiment.category: enum (allowed A|B)".
    """

    def __init__(self, code: str, issues: tuple[str, ...] = ()) -> None:
        super().__init__(code)
        self.code = code
        self.issues = issues


_FENCE = re.compile(r"^\s*```(?:json)?\s*\n(.*)\n\s*```\s*$", re.S)


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    keys = [k for k, _ in pairs]
    if len(keys) != len(set(keys)):
        raise WireError("DUPLICATE_KEY")
    return dict(pairs)


def _reject_constant(_: str) -> Any:
    raise WireError("NON_FINITE_NUMBER")


M = TypeVar("M", bound=_Wire)


def parse_wire(text: str, model: type[M]) -> M:
    if len(text.encode("utf-8")) > MAX_WIRE_BYTES:
        raise WireError("TOO_LARGE")
    fenced = _FENCE.match(text)
    body = fenced.group(1) if fenced else text.strip()
    if not body:
        raise WireError("EMPTY")
    try:
        json.loads(body, object_pairs_hook=_reject_duplicates, parse_constant=_reject_constant)
    except WireError:
        raise
    except ValueError:
        raise WireError("NOT_JSON") from None
    try:
        return model.model_validate_json(body)
    except ValidationError as exc:
        errors = exc.errors(include_url=False, include_input=False)
        first = errors[0]
        issues = tuple(safe_issue(e) for e in errors[:MAX_ISSUES])
        if len(errors) > MAX_ISSUES:
            issues += (f"... and {len(errors) - MAX_ISSUES} more",)
        if first.get("loc") and first["loc"][0] == "contract":
            raise WireError("UNKNOWN_CONTRACT_VERSION", issues) from None
        raise WireError(f"SCHEMA:{first.get('type', 'invalid')}", issues) from None


# ---------------------------------------------------------------- safe repair feedback
MAX_ISSUES: Final = 8
_WIRE_MODELS: Final[tuple[type[_Wire], ...]] = (
    WireObservation,
    WirePattern,
    WireHypothesis,
    WireExperiment,
    WireNeedEvidence,
    WireAbstain,
    WireProposals,
    WirePrediction,
    WireCandidate,
    WirePlan,
    WireCapture,
    WireBrowseReport,
)
# Every name a location may print: schema field names and proposal kinds. Anything
# else in a location (an unknown key, a dict key, a bad tag) came from the model.
SCHEMA_NAMES: Final = frozenset(
    {name for m in _WIRE_MODELS for name in m.model_fields}
    | {"observation", "pattern", "hypothesis", "experiment", "need_evidence", "abstain"}
)
_SAFE_CTX: Final = ("min_length", "max_length", "ge", "le", "gt", "lt", "expected")
_ENUM_SPLIT: Final = re.compile(r",\s*|\s+or\s+")


def safe_location(loc: tuple[int | str, ...], error_type: str) -> str:
    out = ""
    for i, part in enumerate(loc):
        if isinstance(part, int):
            out += f"[{part}]"
            continue
        if part not in SCHEMA_NAMES:
            last = i == len(loc) - 1
            part = "<unexpected key>" if last and error_type == "extra_forbidden" else "<?>"
        out += f".{part}" if out else part
    return out or "<root>"


def safe_issue(error: Mapping[str, Any]) -> str:
    """One validation problem as schema location + type + schema bounds. No model text."""
    error_type = str(error.get("type", "invalid"))
    issue = f"{safe_location(tuple(error.get('loc', ())), error_type)}: {error_type}"
    ctx = error.get("ctx") or {}
    details = []
    for key in _SAFE_CTX:
        if key not in ctx:
            continue
        value = ctx[key]
        if key == "expected" and error_type in {"enum", "literal_error", "union_tag_invalid"}:
            # Pydantic renders the schema's own allowed values here, never the input.
            allowed = [v.strip(" '\"") for v in _ENUM_SPLIT.split(str(value)) if v.strip()]
            details.append("allowed " + "|".join(allowed))
        elif isinstance(value, int | float) and not isinstance(value, bool):
            details.append(f"{key} {value}")
    if error_type == "union_tag_invalid" and "expected_tags" in ctx:
        allowed = [v.strip(" '\"") for v in _ENUM_SPLIT.split(str(ctx["expected_tags"]))]
        details.append("allowed kind " + "|".join(a for a in allowed if a))
    return issue + (f" ({'; '.join(details)})" if details else "")


# ---------------------------------------------------------------- model-facing contract
def _limits(model: type[_Wire], name: str) -> tuple[int, int | None]:
    """(min, max) items or value for a field, read from the schema itself."""
    lo, hi = 0, None
    for meta in model.model_fields[name].metadata:
        for attr in ("min_length", "ge"):
            if getattr(meta, attr, None) is not None:
                lo = getattr(meta, attr)
        for attr in ("max_length", "le"):
            if getattr(meta, attr, None) is not None:
                hi = getattr(meta, attr)
    return lo, hi


def _n(model: type[_Wire], name: str) -> str:
    lo, hi = _limits(model, name)
    return f"{lo}-{hi}"


def text_max() -> int:
    (constraint,) = (m for m in get_args(ShortText)[1:] if hasattr(m, "max_length"))
    return int(constraint.max_length)


LOW_RISK_CATEGORIES: Final = (
    InterventionCategory.ROUTINE_TIMING,
    InterventionCategory.ENVIRONMENT,
    InterventionCategory.TRANSITION_SUPPORT,
    InterventionCategory.COMMUNICATION,
    InterventionCategory.PLAY_ACTIVITY,
)
ESCALATING_CATEGORIES: Final = (
    InterventionCategory.CAREGIVER_COORDINATION,
    InterventionCategory.SLEEP_SCHEDULE,
    InterventionCategory.MEAL_TIMING,
    InterventionCategory.SCREEN_TIME,
)
BLOCKED_CATEGORIES: Final = tuple(
    c
    for c in InterventionCategory
    if c not in {*LOW_RISK_CATEGORIES, *ESCALATING_CATEGORIES, InterventionCategory.OTHER}
)


def _alts(values: Iterable[Any]) -> str:
    return "|".join(f'"{v.value}"' for v in values)


def _shapes() -> dict[str, str]:
    o, p, h, e, n = WireObservation, WirePattern, WireHypothesis, WireExperiment, WireNeedEvidence
    lo_days, hi_days = _limits(e, "max_duration_days")
    return {
        "observation": (
            '{"kind":"observation","evidence_ids":['
            f'{_n(o, "evidence_ids")} evd ids],"statement":text,'
            f'"contexts":[{_n(o, "contexts")} tags]}}'
        ),
        "pattern": (
            '{"kind":"pattern","ref":"P1","observation_ids":['
            f'{_n(p, "observation_ids")} obs ids],"counter_observation_ids":['
            f'{_n(p, "counter_observation_ids")} obs ids],"description":text,'
            f'"contexts":[{_n(p, "contexts")} tags]}}\n'
            "   A pattern needs at least 2 distinct obs ids from CONTEXT; with fewer, propose\n"
            "   no pattern."
        ),
        "hypothesis": (
            '{"kind":"hypothesis","ref":"H1","pattern_refs":['
            f'{_n(h, "pattern_refs")} "P1"-style refs or pat ids],"statement":text,'
            f'"supporting_evidence_ids":[{_n(h, "supporting_evidence_ids")} evd ids],'
            f'"counter_evidence_ids":[{_n(h, "counter_evidence_ids")} evd ids],'
            f'"alternative_explanations":[{_n(h, "alternative_explanations")} texts],'
            f'"known_confounders":[{_n(h, "known_confounders")} texts],'
            f'"falsification_criteria":[{_n(h, "falsification_criteria")} texts],'
            f'"contexts":[{_n(h, "contexts")} tags],"supersedes":null or a hyp id}}\n'
            "   supporting_evidence_ids and counter_evidence_ids hold evd_ ids only (reports or\n"
            "   web captures), never obs_/pat_/hyp_ ids; observations count through patterns."
        ),
        "experiment": (
            '{"kind":"experiment","hypothesis_ref":"H1" or a hyp id,'
            f'"category":{_alts((*LOW_RISK_CATEGORIES, *ESCALATING_CATEGORIES))}|"OTHER",'
            '"description":text,"reversible":true|false,'
            f'"max_duration_days":integer {lo_days}-{hi_days},"burden":{_alts(Burden)},'
            '"comparison":text,"outcome_measure":text}\n'
            f"   category: {_alts(LOW_RISK_CATEGORIES)} are low-risk;\n"
            f"   {_alts(ESCALATING_CATEGORIES)} always need parent review;\n"
            '   "OTHER" when none fits. No other category value exists. Always blocked, so\n'
            f"   never propose: {_alts(BLOCKED_CATEGORIES)}."
        ),
        "need_evidence": (
            '{"kind":"need_evidence","requested_fields":['
            f'{_n(n, "requested_fields")} tags],"rationale":text}}'
        ),
        "abstain": '{"kind":"abstain","reason":text}',
    }


PROPOSAL_KINDS: Final = tuple(_shapes())


def _types_note() -> list[str]:
    return [
        f"Types: text = a JSON string of 1-{text_max()} characters; tag = lower_snake_case",
        "(^[a-z][a-z0-9_]{0,63}$); an id (evd_/obs_/pat_/hyp_ + 32 hex) is copied exactly",
        'from CONTEXT; "P1"/"H1" refer to items you create in this reply.',
    ]


def propose_contract(kinds: Iterable[str] = PROPOSAL_KINDS) -> str:
    """The reply schema for one task, listing only the proposal kinds it may return."""
    allowed = set(kinds)
    wanted = [k for k in PROPOSAL_KINDS if k in allowed] or list(PROPOSAL_KINDS)
    shapes = _shapes()
    lines = [
        f'Reply schema (contract "{WIRE_VERSION}"). Reply with ONE JSON object and nothing',
        "before or after it:",
        f'{{"contract": "{WIRE_VERSION}", '
        f'"proposals": [{_n(WireProposals, "proposals")} proposals]}}',
        "No other top-level keys. Proposal kinds allowed for this task: "
        + ", ".join(f'"{k}"' for k in wanted)
        + ".",
        "Every key shown is required and no other key is allowed (an empty list is [];",
        "an absent optional value is null). Each proposal is exactly one of:",
    ]
    lines += [f" - {shapes[k]}" for k in wanted]
    lines += _types_note()
    lines.append(
        "If a value would break a bound or is not an allowed value, leave that proposal out."
    )
    if "hypothesis" in wanted:
        lines.append("Propose at least two competing hypotheses when you propose any.")
    return "\n".join(lines)


def plan_contract() -> str:
    c = WireCandidate
    _, max_domains = _limits(c, "allowed_domains")
    _, max_predictions = _limits(c, "predictions")
    tail = (
        f'"requested_fields":[{_n(c, "requested_fields")} tags],"rationale":text,'
        f'"predictions":[1-{max_predictions} predictions]}}'
    )
    return "\n".join(
        [
            f'Reply schema (contract "{WIRE_VERSION}"). Reply with ONE JSON object and nothing',
            "before or after it:",
            f'{{"contract": "{WIRE_VERSION}", '
            f'"candidates": [{_n(WirePlan, "candidates")} candidates]}}',
            "Each candidate is the smallest missing observation that could tell the live",
            "hypotheses apart, and is exactly one of (no other keys):",
            ' - {"candidate_id":"lower-id","acquisition_mode":"ASK_PARENT",'
            '"question":"one yes/no question",' + tail,
            ' - {"candidate_id":"lower-id","acquisition_mode":"BROWSE","subject":tag,'
            f'"allowed_domains":[1-{max_domains} host names],' + tail,
            ' A prediction is {"hypothesis_id":a hyp id from CONTEXT,"expected":'
            f"{_alts(PredictedAnswer)}}}. A candidate is only useful when live hypotheses",
            " predict different answers. The question is answerable YES or NO and never asks",
            " the parent to do anything to the child.",
            *_types_note(),
            "candidate_id matches ^[a-z0-9_-]{1,64}$.",
            "Do not rate value, cost or safety; Serene computes those.",
        ]
    )
