"""The web app's Causal Twin: the `causal_twin` read projection.

The kernel's twin (`serene.causal.model.CausalTwin`, wire version
`causal-twin/1`) carries the child id on the twin, on every edge and in every
scope, and the creating actor's id in every provenance. That shape is canonical
(the Maya report pins it) and is not changed. The web gets this projection
instead, built from the same twin and the same provenance projection (#75):

- `nodes`: the map's variables, each with an opaque id derived from its name;
- `edges`: one per twin edge, with the kernel's verdict (`status`, level,
  learning status, validity), its scope contexts, support, counterevidence,
  experiments, the creating actor's *kind* (never its id) and its raw evidence;
  `from_node` / `to_node` name the variables, or are null while unnamed;
- `provenance`: the complete `TwinProvenanceView` for exactly these edges.

Entity ids (`hyp_`, `evd_`, ...) are opaque, randomly minted handles, the same
ones every other parent projection uses. No child, actor or source id is
present anywhere: the builder refuses to return a view that contains one.

Nothing here decides what an edge means. Every field is copied from the twin or
its provenance projection, and the validators check that the two agree, so the
web never has to reconstruct a verdict.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Final, Literal, Self

from pydantic import Field, StringConstraints, model_validator

from serene.causal.model import CausalEdge, RelationshipStatus, SupportItem, build_causal_twin
from serene.causal.provenance import TwinProvenanceView, build_twin_provenance
from serene.domain.base import (
    EntityId,
    EvidenceId,
    ExperimentId,
    HypothesisId,
    KernelModel,
    Sha256Hex,
    ShortText,
    Tag,
    UtcDatetime,
)
from serene.domain.canonical import sha256_hex
from serene.domain.entities import LearningStatus, ValidityWindow
from serene.domain.values import (
    ActorKind,
    DerivationMethod,
    EpistemicLevel,
    ModelRef,
    VerificationStatus,
)
from serene.projections.state import KernelState

WEB_TWIN_VERSION: Final = "causal-twin-web/1"

NodeId = Annotated[str, StringConstraints(pattern=r"^var_[0-9a-f]{32}$")]

# Identifiers that must never reach the browser: children, actors, sources.
_PRIVATE_ID: Final = re.compile(r"\b(?:chd|act|src)_[0-9a-f]{32}\b")
_PRIVATE_KEYS: Final = frozenset({"child_id", "actor_id", "source_id", "user_id"})


def node_id(variable: str) -> str:
    """The opaque, stable web id of a named variable."""
    return "var_" + sha256_hex(f"{WEB_TWIN_VERSION}:variable:{variable}".encode())[:32]


class WebTwinNode(KernelModel):
    """A variable on the map. Its label is the variable's name, never a person's."""

    node_id: NodeId
    type: Literal["VARIABLE"] = "VARIABLE"
    label: Tag


class WebEdgeOrigin(KernelModel):
    """What kind of actor proposed the edge and how: the twin's provenance without the actor id."""

    actor_kind: ActorKind
    method: DerivationMethod
    model: ModelRef | None
    created_at: UtcDatetime
    derived_from: tuple[EntityId, ...]
    source_ids: tuple[EntityId, ...]
    verification_status: VerificationStatus
    supersedes: EntityId | None


class WebTwinEdge(KernelModel):
    edge_id: HypothesisId
    from_node: NodeId | None
    to_node: NodeId | None
    relationship: ShortText
    status: RelationshipStatus
    epistemic_level: EpistemicLevel
    support: tuple[SupportItem, ...] = Field(max_length=512)
    counterevidence: tuple[EntityId, ...] = Field(max_length=512)
    contradicting_outcomes: tuple[EntityId, ...] = Field(max_length=128)
    confounders: tuple[ShortText, ...] = Field(max_length=16)
    alternative_explanations: tuple[ShortText, ...] = Field(max_length=16)
    competing_edges: tuple[HypothesisId, ...] = Field(max_length=32)
    experiments: tuple[ExperimentId, ...] = Field(max_length=64)
    scope_contexts: tuple[Tag, ...] = Field(min_length=1, max_length=16)
    validity: ValidityWindow | None
    learning_status: LearningStatus | None
    origin: WebEdgeOrigin
    raw_evidence: tuple[EvidenceId, ...] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def _placed_on_both_ends_or_neither(self) -> Self:
        if (self.from_node is None) != (self.to_node is None):
            raise ValueError("an edge names both of its variables or neither")
        return self


class WebCausalTwin(KernelModel):
    version: Literal["causal-twin-web/1"] = WEB_TWIN_VERSION
    ledger_head: Sha256Hex
    as_of: UtcDatetime
    nodes: tuple[WebTwinNode, ...] = Field(max_length=2048)
    edges: tuple[WebTwinEdge, ...] = Field(max_length=1024)
    provenance: TwinProvenanceView

    @model_validator(mode="after")
    def _every_edge_is_explained(self) -> Self:
        ids = [n.node_id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate node")
        used = {n for e in self.edges for n in (e.from_node, e.to_node) if n is not None}
        if used != set(ids):
            raise ValueError("nodes are exactly the variables the edges name")
        if self.provenance.ledger_head != self.ledger_head or self.provenance.as_of != self.as_of:
            raise ValueError("the provenance was built from another ledger position")
        detail = {e.edge_id: e for e in self.provenance.edges}
        if len(detail) != len(self.edges) or {e.edge_id for e in self.edges} != set(detail):
            raise ValueError("every edge, and only these edges, carries its provenance")
        for edge in self.edges:
            p = detail[edge.edge_id]
            contradicting = tuple(c.entity_id for c in p.counterevidence if c.contradicting_outcome)
            if (
                p.status is not edge.status
                or p.epistemic_level is not edge.epistemic_level
                or p.learning_status != edge.learning_status
                or p.validity != edge.validity
                or p.scope_contexts != edge.scope_contexts
                or tuple((s.entity_id, s.kind) for s in p.support)
                != tuple((s.entity_id, s.kind) for s in edge.support)
                or tuple(c.entity_id for c in p.counterevidence) != edge.counterevidence
                or contradicting != edge.contradicting_outcomes
                or tuple(x.experiment_id for x in p.experiments) != edge.experiments
                or p.lineage.raw_evidence != edge.raw_evidence
            ):
                raise ValueError(f"edge {edge.edge_id} differs from its provenance")
        return self


def _edge(edge: CausalEdge) -> WebTwinEdge:
    prov = edge.provenance
    return WebTwinEdge(
        edge_id=edge.edge_id,
        from_node=None if edge.cause is None else node_id(edge.cause),
        to_node=None if edge.effect is None else node_id(edge.effect),
        relationship=edge.relationship,
        status=edge.status,
        epistemic_level=edge.epistemic_level,
        support=edge.support,
        counterevidence=edge.counterevidence,
        contradicting_outcomes=edge.contradicting_outcomes,
        confounders=edge.confounders,
        alternative_explanations=edge.alternative_explanations,
        competing_edges=edge.competing_edges,
        experiments=edge.experiments,
        scope_contexts=edge.scope.contexts,
        validity=edge.validity,
        learning_status=edge.learning_status,
        origin=WebEdgeOrigin(
            actor_kind=prov.created_by.kind,
            method=prov.method,
            model=prov.model,
            created_at=prov.created_at,
            derived_from=prov.derived_from,
            source_ids=prov.source_ids,
            verification_status=prov.verification_status,
            supersedes=prov.supersedes,
        ),
        raw_evidence=edge.raw_evidence,
    )


def private_identifiers(payload: object) -> list[str]:
    """Child, actor or source identifiers anywhere in a JSON-compatible payload."""
    found: set[str] = set()

    def walk(value: object) -> None:
        if isinstance(value, Mapping):
            found.update(f"key:{k}" for k in value if k in _PRIVATE_KEYS)
            for v in value.values():
                walk(v)
        elif isinstance(value, list | tuple):
            for v in value:
                walk(v)

    walk(payload)
    found.update(_PRIVATE_ID.findall(json.dumps(payload)))
    return sorted(found)


def build_web_twin(
    state: KernelState,
    now: datetime,
    labels: Mapping[str, tuple[str, str]] | None = None,
) -> WebCausalTwin:
    """The web's twin as of `now`. `labels` name variables and carry no authority."""
    twin = build_causal_twin(state, now, labels)
    edges = tuple(_edge(e) for e in twin.edges)
    variables = sorted({v for e in twin.edges for v in (e.cause, e.effect) if v is not None})
    view = WebCausalTwin(
        ledger_head=twin.ledger_head,
        as_of=now,
        nodes=tuple(WebTwinNode(node_id=node_id(v), label=v) for v in variables),
        edges=edges,
        provenance=build_twin_provenance(state, now, twin),
    )
    leaked = private_identifiers(view.model_dump(mode="json"))
    if leaked:
        raise ValueError(f"the web twin would expose private identifiers: {leaked}")
    return view
