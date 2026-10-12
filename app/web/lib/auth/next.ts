import { SURFACES } from "@/lib/surfaces";

/** Where to go after signing in: one of Serene's own surfaces, never an arbitrary URL. */
export function safeNext(value: string | null | undefined): string {
  const known = SURFACES.map((s) => s.href);
  return value && known.includes(value) ? value : "/today";
}
