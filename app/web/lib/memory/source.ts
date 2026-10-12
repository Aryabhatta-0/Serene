import { MemoryValidationError, parseMemoryDreamView, type MemoryDreamView } from "./model";

// Validated Memory/Dream projection state, delivered through the parent-only
// projection feed. No fixture or direct Git/ledger access on the live route.
export type MemorySource =
  | { status: "unconnected" }
  | { status: "loading" }
  | { status: "error"; reason: string }
  | { status: "ready"; view: MemoryDreamView };

/** No session or selected child. */
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
