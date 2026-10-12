import { parseCausalTwin, TwinValidationError, type CausalTwin } from "./model";
import { pairWithTwin, parseTwinProvenance, type TwinProvenance } from "./provenance-model";

// Where the Causal Twin surface gets its twin from, as a state the view can
// draw honestly. The Realtime projection transport (#33) is implemented, but
// no complete Twin provenance projection is published yet (#75); until it
// is, the surface says so instead of drawing anything.
//
// A ready twin may come with its provenance projection (Issue #75). With it,
// the panel shows the complete chain behind each link; without it, the panel
// shows only what the twin itself carries and says what is missing.
export type TwinSource =
  | { status: "unconnected" }
  | { status: "loading" }
  | { status: "error"; reason: string }
  | { status: "ready"; twin: CausalTwin; provenance?: TwinProvenance | null };

/** The live source today: no family record is connected. */
export const UNCONNECTED: TwinSource = { status: "unconnected" };

/**
 * Validate a payload from the kernel, and its provenance projection if there
 * is one. Anything that does not pass, or a projection that explains a
 * different twin, is an error state, never a partial map.
 */
export function twinSourceFrom(payload: unknown, provenancePayload?: unknown): TwinSource {
  try {
    const twin = parseCausalTwin(payload);
    const provenance =
      provenancePayload === undefined || provenancePayload === null
        ? null
        : pairWithTwin(twin, parseTwinProvenance(provenancePayload));
    return { status: "ready", twin, provenance };
  } catch (error) {
    if (error instanceof TwinValidationError) return { status: "error", reason: error.message };
    throw error;
  }
}
