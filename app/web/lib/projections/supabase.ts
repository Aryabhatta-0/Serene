import type { SupabaseClient } from "@supabase/supabase-js";
import type { FeedStatus, ProjectionFeed } from "./sync";

// The real transport (Issue #33): the snapshot is read from
// serene.projection_state through PostgREST, and changes arrive through
// Supabase Realtime `postgres_changes` on the same table. Both run as the
// signed-in user, so the #8 RLS policies decide what is visible: a parent
// sees their own children's rows, a caregiver only what was granted.
//
// This is the only place the web app names a Serene table, and it names only
// projection_state: the event ledger is never read here.

const COLUMNS = "child_id,projection,state,last_sequence,last_event_hash";
const STATUS: Record<string, FeedStatus> = {
  SUBSCRIBED: "subscribed",
  CLOSED: "closed",
  CHANNEL_ERROR: "error",
  TIMED_OUT: "error",
};

export function supabaseProjectionFeed(client: SupabaseClient): ProjectionFeed {
  return {
    async fetchSnapshot(childId) {
      const { data, error } = await client
        .schema("serene")
        .from("projection_state")
        .select(COLUMNS)
        .eq("child_id", childId);
      if (error) throw new Error(error.message);
      return data ?? [];
    },
    subscribe(childId, { onRow, onStatus }) {
      const channel = client
        .channel(`serene-projections-${childId}`)
        .on(
          "postgres_changes",
          { event: "*", schema: "serene", table: "projection_state", filter: `child_id=eq.${childId}` },
          (payload) => {
            // A projection row is only removed by a rebuild, which writes it
            // again; deletes carry no state and are covered by the next resync.
            if (payload.eventType !== "DELETE") onRow(payload.new);
          },
        )
        .subscribe((status) => onStatus(STATUS[status] ?? "error"));
      return () => {
        void client.removeChannel(channel);
      };
    },
  };
}
