"use client";

import { useEffect, useState } from "react";
import { InvestigationDetail } from "@/components/investigations/InvestigationDetail";
import { ExperimentsView } from "@/components/experiments/ExperimentsView";
import { MemoryView } from "@/components/memory/MemoryView";
import { CausalTwinSurface } from "@/components/causal-twin/CausalTwinSurface";
import { parseDemoState, type DemoState } from "@/lib/demo/model";
import styles from "./demo.module.css";

export function MayaDemoView() {
  const [state, setState] = useState<DemoState | null>(null);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);
  const [checkpoint, setCheckpoint] = useState(-1);
  const [before, setBefore] = useState(false);

  async function reload() {
    // Clear old results immediately, including when reset removed the artifact.
    setState(null); setError(false); setLoading(true); setCheckpoint(-1);
    try {
      const response = await fetch("/demo/maya/state", { cache: "no-store" });
      if (!response.ok) throw new Error("Report unavailable");
      setState(parseDemoState(await response.json()));
    } catch { setError(true); }
    finally { setLoading(false); }
  }
  useEffect(() => { void reload(); }, []);

  const investigations = state && checkpoint >= 0 ? state.snapshots[checkpoint].investigations : state?.investigations;
  return <div className={styles.demo}>
    <aside className={styles.banner} aria-label="Demo mode">
      <strong>DEMO MODE — synthetic Maya scenario</strong>
      <p>Read-only replay of the canonical local report. Offline scripted I/O; real kernel decisions. This is not the production Supabase/Auth path. Approval shown below was recorded through synthetic Telegram; web approval transport (#84) and sign-in (#87) remain open.</p>
      <button className="button" onClick={() => void reload()} disabled={loading}>Reload generated report</button>
    </aside>
    {loading && <p role="status">Reading canonical Maya report…</p>}
    {error && <div role="alert"><h2>Canonical Maya report unavailable or invalid</h2><p>Run these from the repository root, then reload:</p><pre>uv run python scripts/demo_reset.py{"\n"}uv run python scripts/maya_demo.py</pre></div>}
    {state && <>
      <details className={styles.receipt} open>
        <summary>Canonical artifact receipt</summary>
        <p>Source: <code>.demo/maya/report.json</code> · {state.eventCount} validated events</p>
        <p>Report SHA-256: <code data-report-sha>{state.reportSha}</code></p>
        <p>Artifact modification (ns): <code data-artifact-modified>{state.modified}</code></p>
        <p>Ledger head: <code>{state.ledgerHead}</code></p>
        <p>The canonical scenario is deterministic: regeneration changes the file receipt while identical domain results retain the same hash.</p>
      </details>
      <nav aria-label="Maya demo sections" className={styles.nav}>
        <a href="#demo-today">Today / Investigation</a><a href="#demo-experiment">Experiment / Gate</a><a href="#demo-memory">Memory / Dream</a><a href="#demo-twin">Causal Twin</a>
      </nav>
      <section id="demo-today" className={styles.section}>
        <h2>Today · Investigation</h2>
        <label>Recorded investigation checkpoint <select value={checkpoint} onChange={(e) => setCheckpoint(Number(e.target.value))}>
          <option value={-1}>Latest generated state</option>
          {state.snapshots.map((s, i) => <option key={s.sequence} value={i}>Ledger {s.sequence} · {s.investigations[0]?.phase.replaceAll("_", " ")}</option>)}
        </select></label>
        <p>Earlier checkpoints show what was missing and the policy action at that moment. They are replayed from this same report, not a new scenario.</p>
        {investigations?.map((inv) => <div key={inv.investigation_id}><p>Recorded status: <strong data-investigation-status>{inv.status}</strong></p><InvestigationDetail investigation={inv} /></div>)}
      </section>
      <section id="demo-experiment" className={styles.section}>
        <h2>Experiment · Approval and outcome</h2>
        <ExperimentsView source={{ status: "ready", view: state.experiments }} decide={null} />
        <h3>Promotion Gate · Recorded decisions</h3>
        <ul>{state.promotions.map((p) => <li key={p.sequence} data-promotion>Ledger {p.sequence}: {p.granted ? "Granted" : "Denied"} · {p.from} → {p.to} · {p.reasons.join(", ")}</li>)}</ul>
      </section>
      <section id="demo-memory" className={styles.section}>
        <h2>Memory · Dream accepted and rejected patches</h2>
        <MemoryView source={{ status: "ready", view: state.memory }} />
      </section>
      <section id="demo-twin" className={styles.section}>
        <h2>Causal Twin</h2>
        <label><input type="checkbox" checked={before} onChange={(e) => setBefore(e.target.checked)} /> Show recorded before state</label>
        <p>{before ? "Before experiment" : "After experiment and Dream"} · canonical report snapshot</p>
        <CausalTwinSurface source={{ status: "ready", twin: before ? state.twinBefore : state.twinAfter }} />
      </section>
    </>}
  </div>;
}
