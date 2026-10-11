import { LEVEL_NAMES } from "@/lib/causal-twin/provenance";
import type { EpistemicLevel } from "@/lib/causal-twin/model";
import type {
  DreamRun,
  DreamStage,
  MemoryCheck,
  MemoryDreamView,
  MemoryKind,
  MemoryOperation,
  Patch,
  PatchStatus,
} from "./model";

// How the Memory surface words what the kernel recorded. Codes come from the
// kernel (serene.policies.memory_review, serene.memory.dream and the ledger's
// admission); each is explained in plain words where Serene knows the code,
// and the code itself is always shown, so nothing is summarised away.

export const STATUS_LABELS: Record<PatchStatus, string> = {
  COMMITTED: "Kept",
  REJECTED: "Refused",
  PROPOSED: "Awaiting review",
};

export const OPERATION_LABELS: Record<MemoryOperation, string> = {
  CREATE: "New memory",
  UPDATE: "Change to a memory",
  DEPRECATE: "Withdraw a memory",
};

export const KIND_LABELS: Record<MemoryKind, string> = {
  learning: "Learning",
  routine: "Routine",
  pattern: "Pattern",
  child_fact: "About your child",
  caregiver: "Caregiver",
  investigation: "Investigation",
  decision: "Decision",
};

export const STAGE_LABELS: Record<DreamStage, { term: string; description: string }> = {
  ORIENT: { term: "Gathered", description: "Collected what has happened recently." },
  CONSOLIDATE: { term: "Chose", description: "Chose which memories may need writing or withdrawing." },
  REFLECT: { term: "Drafted", description: "Drafted the wording of each memory." },
  CHALLENGE: { term: "Challenged", description: "Looked for recorded evidence against each draft." },
  VERIFY: { term: "Checked", description: "Filled in levels, sources and dates from the record, not the draft." },
  PROPOSE_PATCH: { term: "Proposed", description: "Put each change forward for review." },
};

export const CHECK_LABELS: Record<MemoryCheck, string> = {
  DOCUMENT_FORMAT: "Well-formed",
  CONTRADICTION_SEARCH: "No contradiction found",
  LINEAGE: "Sources trace back to raw evidence",
  PROMOTION_GATE: "Strong enough evidence for this kind of memory",
};

const LEVEL_BY_NAME: Record<string, EpistemicLevel> = {
  RAW_EVIDENCE: 0,
  OBSERVATION: 1,
  PATTERN: 2,
  HYPOTHESIS: 3,
  TESTED_HYPOTHESIS: 4,
  CONTEXTUAL_LEARNING: 5,
};

/** A rung named with its article: "an observation", "a pattern". */
function aLevel(name: string): string {
  const level = LEVEL_BY_NAME[name];
  const words = level === undefined ? name.toLowerCase().replace(/_/g, " ") : LEVEL_NAMES[level].toLowerCase();
  return `${/^[aeiou]/.test(words) ? "an" : "a"} ${words}`;
}

const EXACT: Record<string, string> = {
  ALL_CHECKS_PASSED: "Every check passed.",
  COMMITTED: "Written to memory.",
  COUNTEREVIDENCE_FOUND: "Evidence against at least one draft was found and carried into it.",
  CONTRADICTED_BY_OUTCOME: "An experiment outcome contradicts it.",
  NO_SUBJECT_TO_CHECK: "It does not say what it is about, so it could not be checked.",
  UNKNOWN_SUBJECT: "What it is about is not on record.",
  NO_PARENT_DECISION: "It needs a parent’s decision that has not been recorded.",
  SUBJECT_NOT_IN_LINEAGE: "What it is about is not part of the evidence trail it cites.",
  SOURCES_MISMATCH: "Its sources do not match the record.",
  SOURCES_NOT_IN_PATCH_PROVENANCE: "It lists sources the proposal itself does not rest on.",
  DIFF_PATH_MISMATCH: "The change names a different file from the one it targets.",
  OPERATION_DIFF_MISMATCH: "The change does not match what it says it does.",
  BASE_REVISION_MISMATCH: "It was written against a different version of the memory.",
  STALE_BASE_REVISION: "The memory changed after this was proposed, so it was not applied.",
  PRE_IMAGE_MISMATCH: "The memory no longer reads as this change expected, so it was not applied.",
  REQUIRED_LEVEL_MISMATCH: "It claims a different evidence requirement from the one this kind of memory has.",
  KIND_PATH_MISMATCH: "Its kind does not match where it would be kept.",
  DEPRECATE_MUST_WITHDRAW: "A withdrawal must mark the memory as withdrawn.",
  WITHDRAWAL_MUST_DEPRECATE: "Marking a memory as withdrawn must be done as a withdrawal.",
  CANNOT_CREATE_WITHDRAWN: "A new memory cannot start out withdrawn.",
  TARGET_ALREADY_EXISTS: "A memory already exists there.",
  TARGET_MISSING: "There is no memory there to change.",
  MALFORMED_DIFF: "The proposed change is not well-formed.",
  MALFORMED_DOCUMENT: "The proposed memory is not well-formed.",
  DROPPED_UNKNOWN_SUBJECT: "A draft about something not on record was dropped.",
  DROPPED_INVALID_PATH: "A draft for a place memory cannot be kept was dropped.",
  DROPPED_UNRENDERABLE: "A draft that could not be checked against the record was dropped.",
};

const PREFIXED: Record<string, (detail: string) => string> = {
  COUNTEREVIDENCE_OMITTED: () => "It leaves out recorded evidence against it.",
  UNKNOWN_COUNTEREVIDENCE: () => "It lists evidence against it that is not on record.",
  STATUS_MISMATCH: () => "Its status does not match the record.",
  CONFLICTING_LEARNING: () => "It conflicts with another learning on record.",
  SUBJECT_KIND_NOT_ALLOWED: () => "This kind of item cannot be kept in this part of memory.",
  PROPOSAL_REFUSED: (detail) => `The record refused a proposal: ${explainReason(detail).text}`,
};

export type ReasonText = { code: string; text: string; known: boolean };

/** A recorded reason in plain words. The code is kept so nothing is hidden. */
export function explainReason(code: string): ReasonText {
  if (code in EXACT) return { code, text: EXACT[code], known: true };
  const [head, detail = ""] = code.split(/:(.*)/s, 2);
  const insufficient = /^(\w+?)_BELOW_(\w+)$/.exec(detail);
  if (head === "INSUFFICIENT_EVIDENCE" && insufficient) {
    return {
      code,
      text: `Not enough evidence: it rests on ${aLevel(insufficient[1])}, and this kind of memory needs at least ${aLevel(insufficient[2])}.`,
      known: true,
    };
  }
  if (head in PREFIXED) return { code, text: PREFIXED[head](detail), known: true };
  if (/^SUBJECT_[A-Z]+$/.test(head)) {
    return { code, text: `What it is about is ${head.slice(8).toLowerCase()} in the record.`, known: true };
  }
  if (/_MISMATCH$/.test(head)) {
    return { code, text: "One of its recorded fields does not match the record.", known: true };
  }
  return { code, text: "Recorded reason (Serene has no plain description for this code yet).", known: false };
}

/** The title a patch proposes, read from its diff (the `# Title` line of the new text). */
export function proposedTitle(patch: Patch): string | null {
  for (const line of patch.diff.split("\n")) {
    const match = /^[+ ]# (.+)$/.exec(line);
    if (match) return match[1];
  }
  return null;
}

/** Patches of one run in the order the run proposed them, grouped by outcome. */
export function runPatches(run: DreamRun, view: MemoryDreamView): Record<PatchStatus, Patch[]> {
  const byId = new Map(view.patches.map((p) => [p.patch_id, p]));
  const groups: Record<PatchStatus, Patch[]> = { COMMITTED: [], REJECTED: [], PROPOSED: [] };
  for (const id of run.proposed) {
    const patch = byId.get(id);
    if (patch) groups[patch.status].push(patch);
  }
  return groups;
}

/** Proposals that did not come from a Dream run (a parent's, for instance). */
export function otherPatches(view: MemoryDreamView): Patch[] {
  return view.patches.filter((p) => p.dream_run_id === null);
}

/** Anchor ids: stable, derived from kernel ids, so links can be followed and checked. */
export const anchor = {
  patch: (patchId: string) => `patch-${patchId}`,
  memory: (path: string) => `memory-${path.replace(/[^a-z0-9]+/g, "-")}`,
  node: (path: string, entityId: string) => `${anchor.memory(path)}-${entityId}`,
  run: (runId: string) => `dream-${runId.slice(0, 16)}`,
};
