import { useId, type ReactNode } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { LineMark, type Certainty } from "@/components/notation/LineMark";
import { Icon } from "@/components/system/Icon";
import { LevelLadder } from "@/components/system/LevelLadder";
import { variableLabel } from "@/lib/causal-twin/categories";
import type { LearningStatus } from "@/lib/causal-twin/model";
import {
  KIND_LABELS as ENTITY_LABELS,
  LEARNING_STATUS_LABELS,
  LEVEL_NAMES,
  VERIFICATION_LABELS,
  entityKind,
} from "@/lib/causal-twin/provenance";
import type { DreamRun, MemoryDreamView, MemoryItem, Patch, PatchStatus } from "@/lib/memory/model";
import {
  CHECK_LABELS,
  KIND_LABELS,
  STAGE_LABELS,
  STATUS_LABELS,
  anchor,
  otherPatches,
  runPatches,
} from "@/lib/memory/present";
import type { MemorySource } from "@/lib/memory/source";
import { PatchCard } from "./PatchCard";
import { Entries, Entry, Pair, Pairs, Reasons, Time } from "./parts";
import styles from "./Memory.module.css";

type MemoryViewProps = { source: MemorySource; retry?: ReactNode };

// The Memory surface (Issue #36): Serene's governed, long-term understanding
// of the child. What it keeps and why (each memory with its scope, its level
// on the evidence ladder, when it is due for review, and the trail down to
// raw evidence), and every Dream run: what it proposed, what the fixed review
// kept and what it refused, with the recorded reasons. It is read-only:
// memory is written only by Serene's memory writer after review.
export function MemoryView({ source, retry }: MemoryViewProps) {
  switch (source.status) {
    case "unconnected":
      return (
        <>
          <EmptyState title="No memories yet">
            <p>
              A memory is only kept after review. Each one will link back to the evidence it came from,
              and anything Serene decided not to keep will say why.
            </p>
          </EmptyState>
          <MemoryGuide />
        </>
      );
    case "loading":
      return (
        <div className={styles.loading} role="status">
          <span className="visually-hidden">Loading memory</span>
          <LineMark certainty="unknown" />
          <LineMark certainty="unknown" />
          <LineMark certainty="unknown" />
        </div>
      );
    case "error":
      return (
        <EmptyState title="Memory couldn’t be shown" tone="stopped" actions={retry}>
          <p>
            What Serene sent did not pass its own checks, so nothing is shown rather than showing
            something wrong. Nothing in your family’s memory was changed.
          </p>
        </EmptyState>
      );
    case "ready": {
      const { view } = source;
      if (
        view.memories.length === 0 &&
        view.dream_runs.length === 0 &&
        view.patches.length === 0 &&
        view.unreadable.length === 0
      ) {
        return (
          <EmptyState title="Nothing remembered yet">
            <p>
              Serene has not kept any memories or run any review of what it has learned. Each memory
              will appear here once it has been reviewed and kept.
            </p>
          </EmptyState>
        );
      }
      return <MemoryReview view={view} />;
    }
  }
}

// How memories are grouped: what Serene relies on, what is due a second look,
// and what it has retired (kept visible, never erased).
const MEMORY_GROUPS: readonly { title: string; statuses: readonly LearningStatus[]; note: string }[] = [
  { title: "Relied on now", statuses: ["ACTIVE"], note: "Held within the situations and dates shown." },
  {
    title: "Due a second look",
    statuses: ["NEEDS_REVIEW", "NEEDS_RETEST", "STALE"],
    note: "Past its review date, or something changed since it was tested. Serene does not rely on these until they are looked at again.",
  },
  { title: "Retired", statuses: ["DEPRECATED"], note: "No longer relied on. Kept so the change stays visible." },
];

const STATUS_MARK: Record<LearningStatus, Certainty> = {
  ACTIVE: "tested",
  NEEDS_REVIEW: "observed",
  NEEDS_RETEST: "observed",
  STALE: "superseded",
  DEPRECATED: "superseded",
};

function MemoryReview({ view }: { view: MemoryDreamView }) {
  const memoryOf = new Map(view.memories.filter((m) => m.written_by).map((m) => [m.written_by!, m]));
  const patchById = new Map(view.patches.map((p) => [p.patch_id, p]));
  const memoryHref = (patchId: string) => {
    const memory = memoryOf.get(patchId);
    return memory ? `#${anchor.memory(memory.path)}` : undefined;
  };
  const others = otherPatches(view);
  const count = (status: PatchStatus) => view.patches.filter((p) => p.status === status).length;
  const due = view.memories.filter((m) => m.status !== "ACTIVE" && m.status !== "DEPRECATED").length;

  return (
    <div className={styles.review} data-memory-review>
      <nav className={styles.overview} aria-label="Memory at a glance">
        <a href="#region-memories" className={styles.tile}>
          <span className={styles.tileCount}>{view.memories.length}</span>
          <span className={styles.tileTerm}>{view.memories.length === 1 ? "memory kept" : "memories kept"}</span>
        </a>
        <a href="#region-memories" className={styles.tile} data-attention={due > 0 || undefined}>
          <span className={styles.tileCount}>{due}</span>
          <span className={styles.tileTerm}>due a second look</span>
        </a>
        <a href="#region-dream-runs" className={styles.tile}>
          <span className={styles.tileCount}>{view.dream_runs.length}</span>
          <span className={styles.tileTerm}>{view.dream_runs.length === 1 ? "Dream run" : "Dream runs"}</span>
        </a>
        <a href="#region-dream-runs" className={styles.tile}>
          <span className={styles.tileCount}>
            {count("COMMITTED")}
            <span className={styles.tileSep}> / </span>
            {count("REJECTED")}
            <span className={styles.tileSep}> / </span>
            {count("PROPOSED")}
          </span>
          <span className={styles.tileTerm}>changes kept / refused / awaiting review</span>
        </a>
      </nav>
      <p className={styles.revision}>
        Memory revision: <code className={styles.refId}>{view.memory_head}</code>
      </p>

      <Region title="What Serene remembers" name="memories">
        <p className={styles.intro}>
          Memories are written only by Serene’s memory writer, after a fixed review. Each one shows
          the evidence it rests on. You cannot edit memory here.
        </p>
        {view.memories.length === 0 ? (
          <p className={styles.empty}>Nothing has been kept in memory yet.</p>
        ) : (
          MEMORY_GROUPS.map((group) => {
            const members = view.memories.filter((m) => group.statuses.includes(m.status));
            if (members.length === 0) return null;
            return (
              <div key={group.title} className={styles.memoryGroup} data-memory-group={group.statuses[0]}>
                <div className={styles.groupHead}>
                  <p className={styles.groupTitle}>{group.title}</p>
                  <p className={styles.groupNote}>{group.note}</p>
                </div>
                <ul className={styles.memories}>
                  {members.map((memory) => (
                    <li key={memory.path}>
                      <Memory memory={memory} keptBy={memory.written_by ? patchById.get(memory.written_by) ?? null : null} />
                    </li>
                  ))}
                </ul>
              </div>
            );
          })
        )}
        {view.unreadable.length > 0 ? (
          <div className={styles.unreadable} role="note">
            <p className={styles.subhead}>Files Serene could not read</p>
            <p>
              These files are in memory but do not have the form Serene writes. They are listed, not
              repaired or hidden.
            </p>
            <ul className={styles.items}>
              {view.unreadable.map((u) => (
                <li key={u.path}>
                  <code className={styles.refId}>{u.path}</code>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </Region>

      <Region title="Dream runs" name="dream-runs">
        <p className={styles.intro}>
          Dreaming looks back over what has happened and proposes changes to memory. It cannot write
          memory itself: a fixed review decides what is kept, and every refusal is recorded with its
          reasons.
        </p>
        <DreamFlow />
        {view.dream_runs.length === 0 ? (
          <p className={styles.empty}>No Dream run has been recorded yet.</p>
        ) : (
          <ul className={styles.runs}>
            {view.dream_runs.map((run) => (
              <li key={run.run_id}>
                <Run run={run} view={view} memoryHref={memoryHref} />
              </li>
            ))}
          </ul>
        )}
      </Region>

      {others.length > 0 ? (
        <Region title="Other proposals" name="other-proposals">
          <p className={styles.intro}>Changes to memory proposed outside a Dream run.</p>
          <ul className={styles.patchGrid}>
            {others.map((patch) => (
              <li key={patch.patch_id}>
                <PatchCard patch={patch} memoryHref={memoryHref(patch.patch_id)} headingLevel="h4" />
              </li>
            ))}
          </ul>
        </Region>
      ) : null}
    </div>
  );
}

/** How memory is kept, for a parent who has none to look at yet. It describes Serene, not a family. */
function MemoryGuide() {
  const id = useId();
  return (
    <section className={styles.guide} aria-labelledby={id}>
      <h2 id={id} className={styles.guideTitle}>
        How Serene keeps memory
      </h2>
      <p className={styles.intro}>
        What happened, what Serene believes and what it remembers are kept apart. A belief climbs the evidence
        ladder one rung at a time, and only a reviewed change can write it into memory.
      </p>
      <ol className={styles.ladderGuide} aria-label="The evidence ladder, from the bottom">
        {LADDER_WORDS.map(([term, text]) => (
          <li key={term}>
            <span className={styles.flowStep}>{term}</span>
            <span className={styles.flowText}>{text}</span>
          </li>
        ))}
      </ol>
      <DreamFlow />
    </section>
  );
}

const LADDER_WORDS: readonly (readonly [string, string])[] = [
  ["Raw evidence", "Something reported or captured, exactly as it arrived."],
  ["Observation", "What the evidence says happened, once checked."],
  ["Pattern", "Something seen more than once."],
  ["Hypothesis", "A possible explanation, not tested."],
  ["Tested hypothesis", "Supported by an experiment you approved."],
  ["Contextual learning", "Kept in memory, only for the situations it was tested in, until it is due for review."],
];

/** How a change reaches memory, in four steps. It describes the process, not any family. */
export function DreamFlow() {
  return (
    <ol className={styles.flow} aria-label="How a change reaches memory">
      <li>
        <span className={styles.flowStep}>Dream proposes</span>
        <span className={styles.flowText}>A change drawn from what was recorded.</span>
      </li>
      <li>
        <span className={styles.flowStep}>The review checks it</span>
        <span className={styles.flowText}>Form, contradictions, the trail to raw evidence, and whether the evidence is strong enough.</span>
      </li>
      <li data-branch="">
        <span className={styles.flowStep}>
          <LineMark certainty="tested" className={styles.flowMark} /> Kept: memory changes
        </span>
        <span className={styles.flowStep}>
          <LineMark certainty="refuted" className={styles.flowMark} /> Refused: memory unchanged
        </span>
        <span className={styles.flowText}>A refusal is kept on record with its reasons.</span>
      </li>
    </ol>
  );
}

function Region({ title, name, children }: { title: string; name: string; children: ReactNode }) {
  const id = useId();
  return (
    <section id={`region-${name}`} className={styles.region} aria-labelledby={id} data-region={name}>
      <h2 id={id} className={styles.regionTitle}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Memory({ memory, keptBy }: { memory: MemoryItem; keptBy: Patch | null }) {
  const id = anchor.memory(memory.path);
  const headingId = `${id}-title`;
  const nodeHref = (entityId: string) =>
    memory.lineage.nodes.some((n) => n.entity_id === entityId) ? `#${anchor.node(memory.path, entityId)}` : undefined;
  // The trail reads from the memory's subject down to raw evidence.
  const trail = [...memory.lineage.nodes].sort(
    (a, b) => (b.level ?? -1) - (a.level ?? -1) || a.entity_id.localeCompare(b.entity_id),
  );
  return (
    <article
      id={id}
      className={styles.memory}
      aria-labelledby={headingId}
      data-memory-path={memory.path}
      data-learning-status={memory.status}
    >
      <div className={styles.memoryMain}>
        <p className={styles.memoryMeta}>
          <span className={styles.kind}>{KIND_LABELS[memory.kind]}</span>
          <span className={styles.memoryStatus}>
            <LineMark certainty={STATUS_MARK[memory.status]} className={styles.statusMark} />
            {LEARNING_STATUS_LABELS[memory.status]}
          </span>
          <LevelLadder level={memory.level} />
        </p>
        <h3 id={headingId} className={styles.memoryTitle}>
          {memory.title}
        </h3>
        <div className={styles.memoryBody}>
          {memory.body.split(/\n{2,}/).map((paragraph, i) => (
            <p key={i}>{paragraph}</p>
          ))}
        </div>
        <dl className={styles.scope}>
          <div>
            <dt>Applies in</dt>
            <dd>
              {memory.scope.length > 0 ? (
                <span className={styles.chips}>
                  {memory.scope.map((tag, i) => (
                    <span key={tag} className={styles.chip}>
                      {variableLabel(tag)}
                      {i < memory.scope.length - 1 ? <span className="visually-hidden">, </span> : null}
                    </span>
                  ))}
                </span>
              ) : (
                "No situations recorded."
              )}
            </dd>
          </div>
          {memory.valid_from ? (
            <div>
              <dt>Valid from</dt>
              <dd>
                <Time iso={memory.valid_from} />
              </dd>
            </div>
          ) : null}
          {memory.review_after ? (
            <div>
              <dt>Review after</dt>
              <dd>
                <Time iso={memory.review_after} />
              </dd>
            </div>
          ) : null}
        </dl>
      </div>

      <section className={styles.provenance} aria-labelledby={`${id}-provenance`} data-provenance-for={memory.path}>
        <h4 id={`${id}-provenance`} className={styles.subheading}>
          Where it came from, and why it is kept
        </h4>
        <div className={styles.provenanceGrid}>
          <div className={styles.why}>
            <Pairs>
              <Pair term="Kept by">
                {memory.written_by ? (
                  <a href={`#${anchor.patch(memory.written_by)}`} data-written-by={memory.written_by}>
                    The reviewed change that wrote it
                  </a>
                ) : (
                  "No recorded change wrote this version."
                )}
              </Pair>
              {keptBy?.review?.passed && keptBy.review.checks_passed.length > 0 ? (
                <Pair term="Passed review">
                  <ul className={styles.passed} aria-label="Checks the change passed">
                    {keptBy.review.checks_passed.map((check) => (
                      <li key={check}>
                        <Icon name="check" className={styles.passedIcon} />
                        {CHECK_LABELS[check]}
                      </li>
                    ))}
                  </ul>
                </Pair>
              ) : null}
              <Pair term="About">
                <Entry id={memory.subject} href={nodeHref(memory.subject)} />
              </Pair>
            </Pairs>
            <p className={styles.subhead}>Sources</p>
            <Entries ids={memory.sources} empty="None recorded." hrefOf={nodeHref} label="Sources" />
            <p className={styles.subhead}>Evidence against it</p>
            <Entries ids={memory.counterevidence} empty="Nothing recorded counts against it." label="Evidence against it" />
          </div>

          <div className={styles.trailWrap}>
            <p className={styles.subhead}>Evidence trail, from this memory down to raw evidence</p>
            <ol className={styles.trail} aria-label="Evidence trail, from this memory down to raw evidence">
              {trail.map((node) => (
                <li
                  key={node.entity_id}
                  id={anchor.node(memory.path, node.entity_id)}
                  className={styles.node}
                  data-raw={node.parents.length === 0 || undefined}
                >
                  <span className={styles.ref}>
                    <span className={styles.refLabel}>{ENTITY_LABELS[entityKind(node.entity_id)]}</span>
                    <code className={styles.refId}>{node.entity_id}</code>
                  </span>
                  <span className={styles.nodeMeta}>
                    {node.level === null ? "No evidence level" : `Level ${node.level}: ${LEVEL_NAMES[node.level]}`}
                    {" · "}
                    {VERIFICATION_LABELS[node.verification_status]}
                  </span>
                  {node.parents.length > 0 ? (
                    <span className={styles.nodeParents}>
                      Rests on{" "}
                      {node.parents.map((parent, i) => (
                        <span key={parent}>
                          {i > 0 ? ", " : null}
                          <a href={`#${anchor.node(memory.path, parent)}`}>
                            <code className={styles.refId}>{parent}</code>
                          </a>
                        </span>
                      ))}
                    </span>
                  ) : (
                    <span className={styles.nodeParents}>Raw evidence: the bottom of the trail.</span>
                  )}
                </li>
              ))}
            </ol>
            {memory.lineage.missing.length > 0 ? (
              <div className={styles.missing} role="note">
                <p className={styles.subhead}>Not found in the record</p>
                <p>The trail cites these, but Serene’s record does not hold them, so the trail is incomplete.</p>
                <Entries ids={memory.lineage.missing} empty="" />
              </div>
            ) : null}
          </div>
        </div>
      </section>
    </article>
  );
}

const GROUPS: readonly { status: PatchStatus; empty: string }[] = [
  { status: "COMMITTED", empty: "Nothing from this run was kept." },
  { status: "REJECTED", empty: "Nothing from this run was refused." },
  { status: "PROPOSED", empty: "Nothing from this run is waiting." },
];

function Run({
  run,
  view,
  memoryHref,
}: {
  run: DreamRun;
  view: MemoryDreamView;
  memoryHref: (patchId: string) => string | undefined;
}) {
  const id = anchor.run(run.run_id);
  const groups = runPatches(run, view);
  const last = run.stages[run.stages.length - 1];
  return (
    <article id={id} className={styles.run} aria-labelledby={`${id}-title`} data-run-id={run.run_id} data-complete={run.complete}>
      <header className={styles.runHead}>
        <h3 id={`${id}-title`} className={styles.runTitle}>
          Dream run of <Time iso={run.started_at} />
        </h3>
        <p className={styles.runState}>
          {run.complete
            ? "Finished every step."
            : `Stopped after “${STAGE_LABELS[last.stage].term}”. Nothing after that step was recorded.`}
        </p>
      </header>
      <ol className={styles.stages} aria-label="Steps of this run">
        {run.stages.map((stage) => (
          <li key={stage.stage} className={styles.stage} data-stage={stage.stage}>
            <span className={styles.stageTerm}>{STAGE_LABELS[stage.stage].term}</span>
            <span className={styles.stageText}>{STAGE_LABELS[stage.stage].description}</span>
            {stage.reason_codes.length > 0 ? (
              <Reasons codes={stage.reason_codes} label={`Notes recorded at “${STAGE_LABELS[stage.stage].term}”`} />
            ) : null}
          </li>
        ))}
      </ol>

      <div className={styles.outcomes}>
        {GROUPS.map(({ status, empty }) => (
          <section
            key={status}
            className={styles.group}
            data-group={status}
            aria-label={`${STATUS_LABELS[status]} from this run`}
          >
            <h4 className={styles.groupHeading}>
              <LineMark certainty={status === "COMMITTED" ? "tested" : status === "REJECTED" ? "refuted" : "unknown"} className={styles.groupMark} />
              {STATUS_LABELS[status]} <span className={styles.count}>({groups[status].length})</span>
            </h4>
            {groups[status].length === 0 ? (
              <p className={styles.empty}>{empty}</p>
            ) : (
              <ul className={styles.patches}>
                {groups[status].map((patch) => (
                  <li key={patch.patch_id}>
                    <PatchCard patch={patch} memoryHref={memoryHref(patch.patch_id)} />
                  </li>
                ))}
              </ul>
            )}
          </section>
        ))}
      </div>
    </article>
  );
}
