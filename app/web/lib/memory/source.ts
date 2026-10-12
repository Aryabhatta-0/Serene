import { MemoryValidationError, parseMemoryDreamView, type MemoryDreamView } from "./model";

// Where the Memory surface gets its view from, as a state it can draw
// honestly. The Realtime projection transport (#33) is implemented, but the
// memory view is not a published projection yet (#99); until it is, the
// surface says so instead of drawing anything.
export type MemorySource =
  | { status: "unconnected" }
  | { status: "loading" }
  | { status: "error"; reason: string }
  | { status: "ready"; view: MemoryDreamView };

/** The live source today: no family record is connected. */
export const UNCONNECTED: MemorySource = { status: "unconnected" };

/** Validate a payload from the kernel. Anything that does not pass is an error state. */
export function memorySourceFrom(payload: unknown): MemorySource {
  try {
    return { status: "ready", view: parseMemoryDreamView(payload) };
  } catch (error) {
    if (error instanceof MemoryValidationError) return { status: "error", reason: error.message };
    throw error;
  }
}
