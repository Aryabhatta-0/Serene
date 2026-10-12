import { parseCausalTwin, TwinValidationError, type CausalTwin } from "./model";
import { pairWithTwin, parseTwinProvenance, type TwinProvenance } from "./provenance-model";
import { parseWebTwin } from "./web-model";

// Where the Causal Twin surface gets its twin from, as a state the view can
// draw honestly. The live surface reads the `causal_twin` projection row
// (`twinSourceFromProjection`); the canonical Maya demo and the fixtures read
// the kernel's own twin format with its provenance projection
// (`twinSourceFrom`). Both arrive at the same view model, which holds no
// child or actor id.
//
// A ready twin may come with its provenance projection (Issue #75). With it,
// the panel shows the complete chain behind each link; without it, the panel
// shows only what the twin itself carries and says what is missing.
export type TwinSource =
  | { status: "unconnected" }
  | { status: "loading" }
  | { status: "error"; reason: string }
  | { status: "ready"; twin: CausalTwin; provenance?: TwinProvenance | null };

/** No family record is connected: nobody is signed in, or no child is open. */
export const UNCONNECTED: TwinSource = { status: "unconnected" };

function ready(build: () => TwinSource): TwinSource {
  try {
    return build();
  } catch (error) {
    if (error instanceof TwinValidationError) return { status: "error", reason: error.message };
    throw error;
  }
}

/**
 * Validate a payload in the kernel's twin format, and its provenance
 * projection if there is one. Anything that does not pass, or a projection
 * that explains a different twin, is an error state, never a partial map.
 */
export function twinSourceFrom(payload: unknown, provenancePayload?: unknown): TwinSource {
  return ready(() => {
    const twin = parseCausalTwin(payload);
    const provenance =
      provenancePayload === undefined || provenancePayload === null
        ? null
        : pairWithTwin(twin, parseTwinProvenance(provenancePayload));
    return { status: "ready", twin, provenance };
  });
}

/**
 * The live `causal_twin` projection row. An empty state means the kernel has
 * no hypothesis for this child yet: an empty map, not an error.
 */
export function twinSourceFromProjection(state: Record<string, unknown>, ledgerHead: string): TwinSource {
  if (Object.keys(state).length === 0) return { status: "ready", twin: { ledger_head: ledgerHead, edges: [] } };
  return ready(() => {
    const { twin, provenance } = parseWebTwin(state);
    return { status: "ready", twin, provenance };
  });
}
