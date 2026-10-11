"use client";

import { useEffect, useState } from "react";
import { ProjectionSync, type ProjectionFeed, type SyncState } from "./sync";

export type ProjectionsState = { status: "unconnected" } | SyncState;

/**
 * Live projection state for one child (Issue #33). With no feed or no child
 * (nothing connected, nobody signed in) it stays "unconnected" and never
 * shows anything else.
 */
export function useProjections(feed: ProjectionFeed | null, childId: string | null): ProjectionsState {
  const [state, setState] = useState<ProjectionsState>({ status: "unconnected" });
  useEffect(() => {
    if (!feed || !childId) {
      setState({ status: "unconnected" });
      return;
    }
    const sync = new ProjectionSync(feed, childId, setState);
    sync.start();
    return () => sync.stop();
  }, [feed, childId]);
  return state;
}
