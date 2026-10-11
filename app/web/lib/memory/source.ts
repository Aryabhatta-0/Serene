import { MemoryValidationError, parseMemoryDreamView, type MemoryDreamView } from "./model";

// Where the Memory surface gets its view from, as a state it can draw
// honestly. There is no backend connection yet: projection state is streamed
// in with Issue #33, and until then the surface says so instead of drawing
// anything.
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
