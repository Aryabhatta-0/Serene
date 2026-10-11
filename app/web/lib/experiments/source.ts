import { ExperimentsValidationError, parseExperimentsView, type ExperimentsView } from "./model";

// Where the Experiments surface gets its view from, as a state it can draw
// honestly. There is no backend connection yet: projection state is streamed
// in with Issue #33, and until then the surface says so instead of drawing
// anything.
export type ExperimentsSource =
  | { status: "unconnected" }
  | { status: "loading" }
  | { status: "error"; reason: string }
  | { status: "ready"; view: ExperimentsView };

/** The live source today: no family record is connected. */
export const UNCONNECTED: ExperimentsSource = { status: "unconnected" };

/** Validate a payload from the kernel. Anything that does not pass is an error state. */
export function experimentsSourceFrom(payload: unknown): ExperimentsSource {
  try {
    return { status: "ready", view: parseExperimentsView(payload) };
  } catch (error) {
    if (error instanceof ExperimentsValidationError) return { status: "error", reason: error.message };
    throw error;
  }
}
