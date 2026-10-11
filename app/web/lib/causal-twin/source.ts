import { parseCausalTwin, TwinValidationError, type CausalTwin } from "./model";

// Where the Causal Twin surface gets its twin from, as a state the view can
// draw honestly. There is no backend connection yet: the twin projection will
// be streamed in with Issue #33, and until then the surface says so instead
// of drawing anything.
export type TwinSource =
  | { status: "unconnected" }
  | { status: "loading" }
  | { status: "error"; reason: string }
  | { status: "ready"; twin: CausalTwin };

/** The live source today: no family record is connected. */
export const UNCONNECTED: TwinSource = { status: "unconnected" };

/**
 * Validate a payload from the kernel. Anything that does not pass is an
 * error state, never a partial map.
 */
export function twinSourceFrom(payload: unknown): TwinSource {
  try {
    return { status: "ready", twin: parseCausalTwin(payload) };
  } catch (error) {
    if (error instanceof TwinValidationError) return { status: "error", reason: error.message };
    throw error;
  }
}
