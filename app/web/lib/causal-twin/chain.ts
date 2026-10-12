import {
  citedIds,
  type EdgeProvenance,
  type EvidenceKind,
  type EvidenceOrigin,
  type ExperimentStatus,
  type LifecycleStatus,
  type MissingNode,
  type NodeKind,
  type OutcomeResult,
  type ProvenanceNode,
  type SourceKind,
  type TwinProvenance,
} from "./provenance-model";

// The full provenance panel's reading of one edge (Issues #39, #75): the
// ordered chain from the link down to raw evidence, and everything else the
// link cites with its own chain. It only follows ids the kernel sent; a node
// the kernel could not find stays in the chain as a missing node.

export type ChainEntry =
  | { id: string; depth: number; node: ProvenanceNode; missing: null }
  | { id: string; depth: number; node: null; missing: MissingNode };

export type Chain = {
  /** `trace_lineage` of the link, nearest first. */
  lineage: ChainEntry[];
  /** Cited items off the link's own lineage (outcomes, experiments, the learning), with their chains. */
  alsoCited: ChainEntry[];
  /** Every missing node anywhere behind the link. */
  missing: MissingNode[];
  complete: boolean;
};

function entry(id: string, depth: number, provenance: TwinProvenance): ChainEntry {
  const node = provenance.nodes.get(id);
  if (node) return { id, depth, node, missing: null };
  // parseTwinProvenance guarantees every referenced id is a node or a missing entry.
  const gap = provenance.missing.get(id) ?? { entity_id: id, referenced_by: [] };
  return { id, depth, node: null, missing: gap };
}

export function chainOf(edge: EdgeProvenance, provenance: TwinProvenance): Chain {
  const lineage = edge.lineage.steps.map((s) => entry(s.entity_id, s.depth, provenance));
  const gapsOnLineage = edge.lineage.missing.map((m) => ({
    id: m.entity_id,
    depth: Math.max(0, ...lineage.map((e) => e.depth)) + 1,
    node: null,
    missing: m,
  }));
  const onLineage = new Set([...lineage, ...gapsOnLineage].map((e) => e.id));

  // Everything else the link cites, and everything their own chains reach.
  const seen = new Set<string>(onLineage);
  const queue = [...citedIds(edge)].filter((id) => !seen.has(id)).sort();
  const alsoCited: ChainEntry[] = [];
  while (queue.length > 0) {
    const id = queue.shift()!;
    if (seen.has(id)) continue;
    seen.add(id);
    const item = entry(id, 0, provenance);
    alsoCited.push(item);
    if (item.node) {
      for (const next of [...item.node.parents, ...item.node.raw_evidence, ...item.node.missing]) {
        if (!seen.has(next)) queue.push(next);
      }
    }
  }
  alsoCited.sort((a, b) => {
    const at = a.node?.occurred_at ?? "";
    const bt = b.node?.occurred_at ?? "";
    return at === bt ? a.id.localeCompare(b.id) : bt.localeCompare(at);
  });

  const missing = [...gapsOnLineage, ...alsoCited]
    .map((e) => e.missing)
    .filter((m): m is MissingNode => m !== null);
  return {
    lineage: [...lineage, ...gapsOnLineage],
    alsoCited,
    missing,
    complete: edge.lineage.complete && missing.length === 0,
  };
}

export const NODE_KIND_LABELS: Record<NodeKind, string> = {
  EVIDENCE: "Raw evidence",
  OBSERVATION: "Observation",
  PATTERN: "Pattern",
  HYPOTHESIS: "Link",
  INVESTIGATION: "Question being investigated",
  EXPERIMENT: "Experiment",
  TRIAL: "Experiment trial",
  OUTCOME: "Experiment outcome",
  LEARNING: "Learning",
  OTHER: "Recorded item",
};

export const ORIGIN_LABELS: Record<EvidenceOrigin, string> = {
  FAMILY: "From your family",
  EXTERNAL: "From an outside source",
  MIXED: "From your family and an outside source",
  UNRESOLVED: "Missing provenance: no raw evidence reached",
};

export const EVIDENCE_KIND_LABELS: Record<EvidenceKind, string> = {
  PARENT_REPORT: "Parent report",
  CAREGIVER_REPORT: "Caregiver report",
  DOCUMENT: "Document",
  BROWSER_CAPTURE: "Web page capture",
};

export const SOURCE_KIND_LABELS: Record<SourceKind, string> = {
  TELEGRAM: "Telegram",
  WEB_APP: "Serene web app",
  BROWSER: "Serene’s bounded browser",
  EXTERNAL_DOCUMENT: "External document",
  KERNEL: "Serene’s kernel",
  EVAL_FIXTURE: "Synthetic test fixture",
};

export const EXPERIMENT_STATUS_LABELS: Record<ExperimentStatus, string> = {
  PROPOSED: "Proposed",
  CLASSIFIED: "Safety-checked",
  BLOCKED: "Blocked by a safety rule",
  AWAITING_APPROVAL: "Waiting for your approval",
  APPROVED: "Approved, not started",
  STARTED: "Running",
  COMPLETED: "Finished",
  ABANDONED: "Stopped",
  PARKED_UNRESOLVED: "Parked, unresolved",
};

export const RESULT_LABELS: Record<OutcomeResult, string> = {
  SUPPORTS: "Supports it",
  CONTRADICTS: "Contradicts it",
  INCONCLUSIVE: "Inconclusive",
};

export const LIFECYCLE_LABELS: Record<LifecycleStatus, string> = {
  ACTIVE: "Current",
  SUPERSEDED: "Replaced",
  REFUTED: "Refuted",
};

/** What the provenance projection deliberately leaves out, so the panel cannot show it. */
export const NOT_IN_PROJECTION: readonly string[] = [
  "The words of a raw report or captured page. Raw evidence stays private: the panel shows its kind, channel, time and fingerprint, and the observation Serene derived from it.",
  "Who in your family recorded each item. Only their role is shown.",
];

/** Anchor for one item in the panel, so every provenance link lands on its entry. */
export function anchorOf(id: string): string {
  return `prov-${id}`;
}
