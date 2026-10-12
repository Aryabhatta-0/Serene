// The live Causal Twin: the `causal_twin` projection row's state, as the kernel
// serializes it (`WebCausalTwin.model_dump(mode="json")`, serene/causal/web.py).
//
// It is the twin without any child, actor or source id: the map's variables
// (opaque `var_` ids with their names), the edges with the kernel's verdicts,
// and the complete provenance projection of every edge (#75). `parseWebTwin`
// reads it into the same view model the Maya demo and fixtures use, so the
// same map and provenance panel draw it.
//
// Nothing is derived here. Every verdict is copied from the payload, the
// kernel's invariants are re-checked, the provenance must explain exactly
// these edges, and a payload carrying any private identifier is refused
// outright, so a malformed or leaky row fails closed instead of being drawn.

import { wireReader } from "@/lib/wire";
import {
  ACTOR_KINDS,
  checkEdge,
  checkTwin,
  DERIVATION_METHODS,
  parseContexts,
  parseEdgeFields,
  parseModelRef,
  TwinValidationError,
  VERIFICATION_STATUSES,
  type CausalEdge,
  type CausalTwin,
} from "./model";
import { pairWithTwin, parseTwinProvenance, type TwinProvenance } from "./provenance-model";

export const WEB_TWIN_VERSION = "causal-twin-web/1";

export type WebTwin = { twin: CausalTwin; provenance: TwinProvenance; asOf: string };

const NODE_RE = /^var_[0-9a-f]{32}$/;
// Children, actors and sources: never sent to, or kept by, the browser.
const PRIVATE_ID = /\b(?:chd|act|src)_[0-9a-f]{32}\b/;
const PRIVATE_KEYS = new Set(["child_id", "actor_id", "source_id", "user_id"]);

function fail(path: string, problem: string): never {
  throw new TwinValidationError(`${path}: ${problem}`);
}
const r = wireReader(fail);

function refusePrivateIdentifiers(value: unknown, path: string): void {
  if (typeof value === "string") {
    if (PRIVATE_ID.test(value)) fail(path, "carries a private identifier");
  } else if (Array.isArray(value)) {
    value.forEach((v, i) => refusePrivateIdentifiers(v, `${path}[${i}]`));
  } else if (typeof value === "object" && value !== null) {
    for (const [key, v] of Object.entries(value)) {
      if (PRIVATE_KEYS.has(key)) fail(`${path}.${key}`, "carries a private identifier");
      refusePrivateIdentifiers(v, `${path}.${key}`);
    }
  }
}

function parseEdge(value: unknown, path: string, labels: ReadonlyMap<string, string>): CausalEdge {
  const e = r.object(value, path);
  const node = (key: "from_node" | "to_node") =>
    r.optional(e[key], (v) => {
      if (typeof v !== "string" || !NODE_RE.test(v)) fail(`${path}.${key}`, "expected a node id");
      return labels.get(v) ?? fail(`${path}.${key}`, "names no node");
    });
  const cause = node("from_node");
  const effect = node("to_node");
  if ((cause === null) !== (effect === null)) fail(path, "an edge names both of its variables or neither");
  const o = r.object(e.origin, `${path}.origin`);
  const { edge_id, relationship, ...rest } = parseEdgeFields(e, path);
  return checkEdge(
    {
      edge_id,
      relationship,
      cause,
      effect,
      ...rest,
      scope: { contexts: parseContexts(e.scope_contexts, `${path}.scope_contexts`) },
      provenance: {
        created_by: { kind: r.oneOf(o.actor_kind, ACTOR_KINDS, `${path}.origin.actor_kind`) },
        created_at: r.timestamp(o.created_at, `${path}.origin.created_at`),
        method: r.oneOf(o.method, DERIVATION_METHODS, `${path}.origin.method`),
        model: parseModelRef(o.model, `${path}.origin.model`),
        derived_from: r.ids(o.derived_from, `${path}.origin.derived_from`, 256),
        source_ids: r.ids(o.source_ids, `${path}.origin.source_ids`, 256),
        verification_status: r.oneOf(o.verification_status, VERIFICATION_STATUSES, `${path}.origin.verification_status`),
        supersedes: r.optional(o.supersedes, (s) => r.id(s, `${path}.origin.supersedes`)),
      },
    },
    path,
  );
}

/** Each edge's own fields agree with its provenance entry (WebCausalTwin._every_edge_is_explained). */
function checkExplained(twin: CausalTwin, provenance: TwinProvenance): void {
  const same = (a: readonly string[], b: readonly string[]) => a.length === b.length && a.every((x, i) => x === b[i]);
  for (const edge of twin.edges) {
    const p = provenance.edges.get(edge.edge_id)!;
    const path = `causal_twin.provenance.edges.${edge.edge_id}`;
    if (
      p.learning_status !== edge.learning_status ||
      p.validity?.valid_from !== edge.validity?.valid_from ||
      p.validity?.review_after !== edge.validity?.review_after ||
      !same(p.scope_contexts, edge.scope.contexts) ||
      !same(p.support.map((s) => `${s.kind}:${s.entity_id}`), edge.support.map((s) => `${s.kind}:${s.entity_id}`)) ||
      !same(p.counterevidence.map((c) => c.entity_id), edge.counterevidence) ||
      !same(p.counterevidence.filter((c) => c.contradicting_outcome).map((c) => c.entity_id), edge.contradicting_outcomes) ||
      !same(p.experiments.map((x) => x.experiment_id), edge.experiments)
    ) {
      fail(path, "differs from the edge it explains");
    }
  }
}

/** Validate a `causal_twin` projection state, or throw TwinValidationError. */
export function parseWebTwin(value: unknown): WebTwin {
  refusePrivateIdentifiers(value, "causal_twin");
  const v = r.object(value, "causal_twin");
  if (v.version !== WEB_TWIN_VERSION) fail("causal_twin.version", `expected ${WEB_TWIN_VERSION}`);
  const ledgerHead = r.sha256(v.ledger_head, "causal_twin.ledger_head");
  const asOf = r.timestamp(v.as_of, "causal_twin.as_of");
  const labels = new Map<string, string>();
  r.array(v.nodes, "causal_twin.nodes", 2048).forEach((n, i) => {
    const node = r.object(n, `causal_twin.nodes[${i}]`);
    const nodeId = node.node_id;
    if (typeof nodeId !== "string" || !NODE_RE.test(nodeId)) fail(`causal_twin.nodes[${i}].node_id`, "expected a node id");
    if (node.type !== "VARIABLE") fail(`causal_twin.nodes[${i}].type`, "expected VARIABLE");
    if (labels.has(nodeId)) fail(`causal_twin.nodes[${i}]`, "duplicate node");
    labels.set(nodeId, r.tag(node.label, `causal_twin.nodes[${i}].label`));
  });
  const edges = r
    .array(v.edges, "causal_twin.edges", 1024)
    .map((e, i) => parseEdge(e, `causal_twin.edges[${i}]`, labels));
  const used = new Set(edges.flatMap((e) => (e.cause === null ? [] : [e.cause, e.effect])));
  if (used.size !== labels.size || [...labels.values()].some((label) => !used.has(label))) {
    fail("causal_twin.nodes", "nodes are exactly the variables the edges name");
  }
  const twin = checkTwin({ ledger_head: ledgerHead, edges }, "causal_twin");
  const provenance = pairWithTwin(twin, parseTwinProvenance(v.provenance));
  if (provenance.as_of !== asOf) fail("causal_twin.provenance.as_of", "built at another time");
  checkExplained(twin, provenance);
  return { twin, provenance, asOf };
}
