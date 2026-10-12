"use client";

import { useEffect, useState } from "react";
import { InvestigationDetail } from "@/components/investigations/InvestigationDetail";
import { ExperimentsView } from "@/components/experiments/ExperimentsView";
import { MemoryView } from "@/components/memory/MemoryView";
import { CausalTwinSurface } from "@/components/causal-twin/CausalTwinSurface";
import { parseDemoState, type DemoState } from "@/lib/demo/model";
import { LEVEL_NAMES } from "@/lib/causal-twin/provenance";
import styles from "./demo.module.css";

const CHAPTERS = [
  { id: "demo-today", title: "Follow the clues", detail: "What Maya’s family reported and what evidence adds" },
  { id: "demo-experiment", title: "Try one small change", detail: "A parent-approved pickup trial" },
  { id: "demo-memory", title: "Keep a useful lesson", detail: "What may help this family, and what we still can’t say" },
  { id: "demo-twin", title: "Compare the explanations", detail: "What changed, and what remains uncertain" },
];

function checkpointLabel(phase: string): string {
  const labels: Record<string, string> = {
    RETRIEVING_CONTEXT: "Gathering the first reports",
    FORMING_HYPOTHESES: "Keeping explanations open",
    NEEDS_EVIDENCE: "Choosing what to check",
    ASKING_HUMAN: "Waiting for a parent’s answer",
    VERIFYING: "Checking a source",
    EVALUATING: "Reviewing what the evidence supports",
    RESEARCHING: "Looking for useful information",
    NEEDS_APPROVAL: "Asking before a trial",
    COMPLETE: "Investigation finished",
  };
  return labels[phase] ?? phase.toLowerCase().replaceAll("_", " ");
}

function reviewLabel(level: number): string {
  return LEVEL_NAMES[level as keyof typeof LEVEL_NAMES]?.toLowerCase() ?? "recorded level";
}

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
      <div>
        <strong>A made-up example</strong>
        <p>No real family’s data is shown. The parent-approved trial is part of this fictional story.</p>
      </div>
    </aside>
    {loading && <p role="status">Loading the example…</p>}
    {error && <div role="alert"><h2>This example is temporarily unavailable</h2><p>Please refresh the page later.</p></div>}
    {state && <>
      <section className={styles.overview} aria-labelledby="shared-summary">
        <p className={styles.audience}>For parents, caregivers, teachers, and clinicians</p>
        <h2 id="shared-summary">A shared summary</h2>
        <p className={styles.overviewLead}>Use this example to see what was reported, what was tried and what the result can—and cannot—tell us. It is a conversation aid, not a diagnosis.</p>
        <dl className={styles.takeaways}>
          <div><dt>What was reported</dt><dd>Maya’s parent reported difficult daycare pickups.</dd></div>
          <div><dt>What was tried</dt><dd>Her parent approved a five-minute warning before leaving daycare.</dd></div>
          <div><dt>What the result suggests</dt><dd>Her parent reported calmer pickups on most days with the warning. A difficult transition may matter in this situation.</dd></div>
          <div><dt>What remains uncertain</dt><dd>Fatigue and hunger are still possible. This one example cannot explain other children or situations.</dd></div>
        </dl>
        <p className={styles.summaryNote}>This is a fictional child and a recorded example. In real care, parents decide what to try; caregivers, teachers and clinicians can bring their observations and context.</p>
      </section>
      <nav aria-label="Story chapters" className={styles.nav}>
        <ol>
          {CHAPTERS.map((chapter, index) => <li key={chapter.id}>
            <a href={`#${chapter.id}`}><span className={styles.chapterNumber}>{index + 1}</span><span><strong>{chapter.title}</strong><small>{chapter.detail}</small></span></a>
          </li>)}
        </ol>
      </nav>
      <section id="demo-today" className={styles.section} aria-labelledby="chapter-clues">
        <p className={styles.step}>Chapter 1</p>
        <h2 id="chapter-clues">Follow the clues</h2>
        <p className={styles.explainer}>Three explanations remain in play: tiredness, hunger, or a difficult transition. Serene asks for relevant evidence and checks whether its source is trustworthy. A checked source does not prove which explanation is right.</p>
        <div className={styles.detailDisclosure}>
          <h3>See how Serene reviewed the story</h3>
          <label className={styles.checkpoint}>Choose a moment in the story <select value={checkpoint} onChange={(e) => setCheckpoint(Number(e.target.value))}>
            <option value={-1}>Latest recorded moment</option>
            {state.snapshots.map((s, i) => <option key={s.sequence} value={i}>Step {i + 1} of {state.snapshots.length} — {checkpointLabel(s.investigations[0]?.phase ?? "")}</option>)}
          </select></label>
          <p className={styles.hint}>Choose an earlier moment to see what Serene knew then. Each moment comes from the same recorded story.</p>
          {investigations?.map((inv) => <div key={inv.investigation_id}><InvestigationDetail investigation={inv} variant="brief" /></div>)}
        </div>
      </section>
      <section id="demo-experiment" className={styles.section} aria-labelledby="chapter-trial">
        <p className={styles.step}>Chapter 2</p>
        <h2 id="chapter-trial">Try one small change</h2>
        <p className={styles.explainer}>Before anything changed, a parent approved a reversible trial: give a five-minute warning before leaving daycare. The example below shows what changed and what the parent noticed afterward.</p>
        <div className={styles.takeaway}>
          <strong>What the parent noticed</strong>
          <p>Pickups were calmer on most days with the five-minute warning. That is encouraging for this family, but it does not prove the warning will help every child.</p>
        </div>
        <details className={styles.detailDisclosure} open>
          <summary>See the trial record</summary>
          <ExperimentsView source={{ status: "ready", view: state.experiments }} decide={null} />
          <details className={styles.review} open>
            <summary>How Serene reviewed the result</summary>
            <p>Serene checks evidence in small steps before saving a lesson. It cannot turn one result into a rule for every child or situation.</p>
            <ol>{state.promotions.map((p, i) => <li key={p.sequence} data-promotion>
              Review {i + 1}: {p.granted ? `moved from ${reviewLabel(p.from)} to ${reviewLabel(p.to)}` : `did not move from ${reviewLabel(p.from)} to ${reviewLabel(p.to)}`}.
            </li>)}</ol>
          </details>
        </details>
      </section>
      <section id="demo-memory" className={styles.section} aria-labelledby="chapter-memory">
        <p className={styles.step}>Chapter 3</p>
        <h2 id="chapter-memory">Keep a useful lesson</h2>
        <p className={styles.explainer}>The example keeps a small lesson about daycare pickup and sets aside a broader claim about every child. Serene checks what supports a lesson before adding it to memory.</p>
        <div className={styles.takeaway}>
          <strong>The lesson kept</strong>
          <p>A five-minute heads-up may help with weekday daycare pickup. Serene keeps that lesson tied to this situation and the dates it was observed.</p>
          <strong>The claim set aside</strong>
          <p>There is not enough evidence to say that every difficult transition has the same cause.</p>
        </div>
        <details className={styles.detailDisclosure} open>
          <summary>See what Serene kept and why</summary>
          <MemoryView source={{ status: "ready", view: state.memory }} />
        </details>
      </section>
      <section id="demo-twin" className={styles.section} aria-labelledby="chapter-compare">
        <p className={styles.step}>Chapter 4</p>
        <h2 id="chapter-compare">Compare the explanations</h2>
        <p className={styles.explainer}>The trial added support to the idea that transitions can make daycare pickup harder. Fatigue and hunger remain possible, but untested. Compare the two views to see which ideas gained support and which remain open.</p>
        <div className={styles.takeaway}>
          <strong>More support after the trial</strong>
          <p>The warning is linked with calmer pickups in this example. Tiredness and hunger are still possible explanations; this story did not test them.</p>
        </div>
        <details className={styles.detailDisclosure}>
          <summary>Explore how the explanations changed</summary>
          <label className={styles.compare}><input type="checkbox" checked={before} onChange={(e) => setBefore(e.target.checked)} /> Compare with the view before the trial</label>
          <p className={styles.hint}>{before ? "Before the parent-approved trial" : "After the trial and memory review"}</p>
          <CausalTwinSurface
            source={{
              status: "ready",
              twin: before ? state.twinBefore : state.twinAfter,
              provenance: before ? state.provenanceBefore : state.provenanceAfter,
            }}
          />
        </details>
      </section>
    </>}
  </div>;
}
