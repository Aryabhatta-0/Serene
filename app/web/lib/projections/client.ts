import { createClient } from "@supabase/supabase-js";
import type { SupabaseConfig } from "./config";
import { supabaseProjectionFeed } from "./supabase";
import type { ProjectionFeed } from "./sync";

/**
 * The live projection feed for a configured Supabase project (Issue #33). It
 * runs as whoever is signed in, so RLS decides what it can see. Web sign-in is
 * not built yet (#84), so no page creates one; until then surfaces stay
 * "unconnected" rather than showing anything else.
 */
export function projectionFeed(config: SupabaseConfig): ProjectionFeed {
  return supabaseProjectionFeed(
    createClient(config.url, config.anonKey, { auth: { persistSession: true, autoRefreshToken: true } }),
  );
}
