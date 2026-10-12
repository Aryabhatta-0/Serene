import { parseInvestigations } from "@/lib/investigations/model";
import { parseExperimentsView } from "@/lib/experiments/model";
import { parseMemoryDreamView } from "@/lib/memory/model";
import { parseCausalTwin } from "@/lib/causal-twin/model";
import { wireReader } from "@/lib/wire";

const r = wireReader((path, problem): never => { throw new Error(`${path}: ${problem}`); });

/** Validate the server adapter's views through the production UI parsers. */
export function parseDemoState(value: unknown) {
  const v = r.object(value, "demo");
  return {
    reportSha: r.sha256(v.report_sha256, "demo.report_sha256"),
    modified: r.text(v.artifact_modified_ns, "demo.artifact_modified_ns"),
    ledgerHead: r.sha256(v.ledger_head, "demo.ledger_head"),
    eventCount: r.integer(v.event_count, "demo.event_count", 1, 10000),
    investigations: parseInvestigations(v.investigations),
    snapshots: r.array(v.snapshots, "demo.snapshots", 256).map((item) => {
      const s = r.object(item, "snapshot");
      return { sequence: r.integer(s.sequence, "snapshot.sequence", 1, 10000), investigations: parseInvestigations(s.investigations) };
    }),
    experiments: parseExperimentsView(v.experiments),
    memory: parseMemoryDreamView(v.memory),
    twinBefore: parseCausalTwin(v.twin_before),
    twinAfter: parseCausalTwin(v.twin_after),
    promotions: r.array(v.promotions, "demo.promotions", 64).map((item) => {
      const p = r.object(item, "promotion");
      return {
        sequence: r.integer(p.sequence, "promotion.sequence", 1, 10000),
        granted: r.bool(p.granted, "promotion.granted"),
        from: r.integer(p.from_level, "promotion.from_level", 0, 5),
        to: r.integer(p.to_level, "promotion.to_level", 0, 5),
        reasons: r.reasons(p.reason_codes, "promotion.reason_codes", 64),
      };
    }),
  };
}

export type DemoState = ReturnType<typeof parseDemoState>;
