import { createClient, type SupabaseClient } from "@supabase/supabase-js";
import type { SupabaseConfig } from "@/lib/projections/config";

// The one Supabase client in the browser (Issue #87). Sign-in, the guardian
// lookup and the Realtime projection feed share it, so the projection reads
// and the Realtime channel always run as whoever is signed in, and RLS decides
// what they see. The session is kept in this browser's storage and refreshed
// by supabase-js; nothing here reads or stores a token itself.
let cached: { key: string; client: SupabaseClient } | null = null;

export function browserClient(config: SupabaseConfig): SupabaseClient {
  const key = `${config.url}\n${config.anonKey}`;
  if (cached?.key !== key) {
    cached = {
      key,
      client: createClient(config.url, config.anonKey, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          // Email and password only: no session is ever taken from a URL.
          detectSessionInUrl: false,
          storageKey: "serene-auth",
        },
      }),
    };
  }
  return cached.client;
}
