import { useId, type ReactNode } from "react";
import { EmptyState } from "@/components/layout/EmptyState";
import { LineMark } from "@/components/notation/LineMark";
import { variableLabel } from "@/lib/causal-twin/categories";
import {
  KIND_LABELS as ENTITY_LABELS,
  LEARNING_STATUS_LABELS,
  LEVEL_NAMES,
  VERIFICATION_LABELS,
  entityKind,
} from "@/lib/causal-twin/provenance";
import type { DreamRun, MemoryDreamView, MemoryItem, PatchStatus } from "@/lib/memory/model";
import {
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

// The Memory surface (Issue #36): what Serene keeps in long-term memory and
// where each memory came from, and every Dream run with what it proposed,
// what was kept and what was refused, with the recorded reasons. It is
// read-only: memory is written only by Serene's memory writer after review.
export function MemoryView({ source, retry }: MemoryViewProps) {
  switch (source.status) {
    case "unconnected":
      return (
        <EmptyState title="No memories yet">
          <p>
            A memory is only kept after review. Each one will link back to the evidence it came from,
            and anything Serene decided not to keep will say why.
          </p>
        </EmptyState>
      );
    case "loading":
      return (
        <div className={styles.loading} role="status">
          <span className="visually-hidden">Loading memory</span>
          <LineMark certainty="unknown" />
          <LineMark certainty="unknown" />
        </div>
      );
    case "error":
      return (
        <EmptyState title="Memory couldn’t be shown">
          <p>
            What Serene sent did not pass its own checks, so nothing is shown rather than showing
            something wrong. Nothing in your family’s memory was changed.
          </p>
          {retry ? <p>{retry}</p> : null}
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

function MemoryReview({ view }: { view: MemoryDreamView }) {
  const memoryOf = new Map(view.memories.filter((m) => m.written_by).map((m) => [m.written_by!, m]));
  const memoryHref = (patchId: string) => {
    const memory = memoryOf.get(patchId);
    return memory ? `#${anchor.memory(memory.path)}` : undefined;
  };
  const others = otherPatches(view);
  return (
    <div className={styles.review} data-memory-review>
      <p>Memory revision: <code className={styles.refId}>{view.memory_head}</code></p>
      <Region title="What Serene remembers" name="memories">
        <p className={styles.intro}>
          Memories are written only by Serene’s memory writer, after a fixed review. Each one shows
          the evidence it rests on. You cannot edit memory here.
        </p>
        {view.memories.length === 0 ? (
          <p className={styles.empty}>Nothing has been kept in memory yet.</p>
        ) : (
          <ul className={styles.memories}>
            {view.memories.map((memory) => (
              <li key={memory.path}>
                <Memory memory={memory} />
              </li>
            ))}
          </ul>
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
          <ul className={styles.patches}>
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

function Region({ title, name, children }: { title: string; name: string; children: ReactNode }) {
  const id = useId();
  return (
    <section className={styles.region} aria-labelledby={id} data-region={name}>
      <h2 id={id} className={styles.regionTitle}>
        {title}
      </h2>
      {children}
    </section>
  );
}

function Memory({ memory }: { memory: MemoryItem }) {
  const id = anchor.memory(memory.path);
  const headingId = `${id}-title`;
  const nodeHref = (entityId: string) =>
    memory.lineage.nodes.some((n) => n.entity_id === entityId) ? `#${anchor.node(memory.path, entityId)}` : undefined;
  // The trail reads from the memory's subject down to raw evidence.
  const trail = [...memory.lineage.nodes].sort(
    (a, b) => (b.level ?? -1) - (a.level ?? -1) || a.entity_id.localeCompare(b.entity_id),
  );
  return (
    <article id={id} className={styles.memory} aria-labelledby={headingId} data-memory-path={memory.path}>
      <p className={styles.memoryMeta}>
        <span>{KIND_LABELS[memory.kind]}</span>
        <span>{LEARNING_STATUS_LABELS[memory.status]}</span>
        <span>
          {memory.level === null ? "No evidence level" : `Level ${memory.level} of 5: ${LEVEL_NAMES[memory.level]}`}
        </span>
      </p>
      <h3 id={headingId} className={styles.memoryTitle}>
        {memory.title}
      </h3>
      <div className={styles.memoryBody}>
        {memory.body.split(/\n{2,}/).map((paragraph, i) => (
          <p key={i}>{paragraph}</p>
        ))}
      </div>
      <Pairs>
        <Pair term="Applies in">
          {memory.scope.length > 0 ? memory.scope.map(variableLabel).join(", ") : "No situations recorded."}
        </Pair>
        {memory.valid_from ? (
          <Pair term="Valid from">
            <Time iso={memory.valid_from} />
          </Pair>
        ) : null}
        {memory.review_after ? (
          <Pair term="Review after">
            <Time iso={memory.review_after} />
          </Pair>
        ) : null}
      </Pairs>

      <section className={styles.provenance} aria-labelledby={`${id}-provenance`} data-provenance-for={memory.path}>
        <h4 id={`${id}-provenance`} className={styles.subheading}>
          Where it came from
        </h4>
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
          <Pair term="About">
            <Entry id={memory.subject} href={nodeHref(memory.subject)} />
          </Pair>
        </Pairs>
        <p className={styles.subhead}>Sources</p>
        <Entries ids={memory.sources} empty="None recorded." hrefOf={nodeHref} label="Sources" />
        <p className={styles.subhead}>Evidence against it</p>
        <Entries ids={memory.counterevidence} empty="Nothing recorded counts against it." label="Evidence against it" />

        <p className={styles.subhead}>Evidence trail, from this memory down to raw evidence</p>
        <ol className={styles.trail} aria-label="Evidence trail, from this memory down to raw evidence">
          {trail.map((node) => (
            <li key={node.entity_id} id={anchor.node(memory.path, node.entity_id)} className={styles.node}>
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
    <article id={id} className={styles.run} aria-labelledby={`${id}-title`} data-run-id={run.run_id}>
      <h3 id={`${id}-title`} className={styles.runTitle}>
        Dream run of <Time iso={run.started_at} />
      </h3>
      <p className={styles.runState}>
        {run.complete
          ? "Finished every step."
          : `Stopped after “${STAGE_LABELS[last.stage].term}”. Nothing after that step was recorded.`}
      </p>
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

      {GROUPS.map(({ status, empty }) => (
        <section key={status} className={styles.group} data-group={status} aria-label={`${STATUS_LABELS[status]} from this run`}>
          <h4 className={styles.subheading}>
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
    </article>
  );
}
