import { browserClient } from "@/lib/auth/client";
import type { SupabaseConfig } from "./config";
import { supabaseProjectionFeed } from "./supabase";
import type { ProjectionFeed } from "./sync";

/**
 * The live projection feed for a configured Supabase project (Issue #33). It
 * shares the signed-in browser client (#87), so RLS decides what it can see.
 * Surfaces get it through the family record (components/session), which
 * passes it on only once someone is signed in and a child is chosen.
 */
export function projectionFeed(config: SupabaseConfig): ProjectionFeed {
  return supabaseProjectionFeed(browserClient(config));
}
