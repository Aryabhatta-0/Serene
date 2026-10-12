import { ExperimentsValidationError, parseExperimentsView, type ExperimentsView } from "./model";

// Where the Experiments surface gets its view from, as a state it can draw
// honestly. LiveExperiments validates the selected child's streamed projection
// before handing it to the existing surface.
export type ExperimentsSource =
  | { status: "unconnected" }
  | { status: "loading" }
  | { status: "error"; reason: string }
  | { status: "ready"; view: ExperimentsView };

/** No authenticated family record or experiments projection is available. */
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
