"use client";

import { useEffect, useId, useRef, useState, type ReactNode, type Ref } from "react";
import { LineMark } from "@/components/notation/LineMark";
import { CATEGORIES, categorize, variableLabel } from "@/lib/causal-twin/categories";
import type { CausalEdge, CausalTwin } from "@/lib/causal-twin/model";
import {
  ACTOR_LABELS,
  KIND_LABELS,
  LEARNING_STATUS_LABELS,
  LEVEL_NAMES,
  METHOD_LABELS,
  NOT_IN_TWIN,
  ROLE_LABELS,
  VERIFICATION_LABELS,
  againstFor,
  competingLinks,
  entityKind,
  formatDate,
  lineageOf,
  supersessionOf,
  supportFor,
  verdictReason,
  type EvidenceItem,
  type LinkRef,
} from "@/lib/causal-twin/provenance";
import styles from "./EdgeProvenance.module.css";

// Long lists show this many items until the parent asks for the rest; the
// count of what is hidden is always stated.
const SHOWN = 6;

type EdgeProvenanceProps = {
  edge: CausalEdge;
  twin: CausalTwin;
  /** Choose another link (a rival, a replacement) without leaving the panel. */
  onSelectEdge: (edgeId: string) => void;
};

// Why Serene holds the selected link the way it does (Issue #39): the
// verdict, the evidence on each side, the experiments, where and when it
// holds, what else could explain it, what it replaced, and the chain down to
// raw evidence. Every item is a recorded id from the twin, labelled by what
// it is; nothing is scored, summarised away or made up.
export function EdgeProvenance({ edge, twin, onSelectEdge }: EdgeProvenanceProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const jumped = useRef(false);
  // After moving to another link from inside the panel, keep keyboard focus
  // here rather than losing it with the button that was pressed.
  useEffect(() => {
    if (jumped.current) headingRef.current?.focus();
    jumped.current = false;
  }, [edge.edge_id]);
  const go = (edgeId: string) => {
    jumped.current = true;
    onSelectEdge(edgeId);
  };

  const support = supportFor(edge);
  const against = againstFor(edge);
  const lineage = lineageOf(edge, twin);
  const supersession = supersessionOf(edge, twin);
  const rivals = competingLinks(edge, twin);
  const { provenance } = edge;

  return (
    <div className={styles.provenance} data-provenance-for={edge.edge_id}>
      <Section title="Why it is drawn this way" headingRef={headingRef} name="verdict">
        <p>{verdictReason(edge)}</p>
        <dl className={styles.pairs}>
          <div>
            <dt>Evidence ladder</dt>
            <dd>
              Level {edge.epistemic_level} of 5: {LEVEL_NAMES[edge.epistemic_level]}
            </dd>
          </div>
        </dl>
      </Section>

      <Section title="Evidence for it" name="support">
        <Evidence items={support} empty="Nothing recorded supports it yet." />
      </Section>

      <Section title="Evidence against it" name="against">
        <Evidence items={against} empty="Nothing recorded counts against it." />
      </Section>

      <Section title="Experiments" name="experiments">
        <Ids
          ids={edge.experiments}
          label={KIND_LABELS.experiment}
          empty="No experiment has been set up for this link."
        />
        {edge.experiments.length > 0 ? (
          <p className={styles.aside}>
            Their outcomes are listed above, for and against. The map does not say which outcome
            came from which experiment.
          </p>
        ) : null}
      </Section>

      <Section title="Where and when it holds" name="scope">
        <dl className={styles.pairs}>
          <div>
            <dt>Situations</dt>
            <dd>{edge.scope.contexts.map(variableLabel).join(", ")}</dd>
          </div>
          {edge.validity ? (
            <>
              <div>
                <dt>Valid from</dt>
                <dd>
                  <Time iso={edge.validity.valid_from} />
                </dd>
              </div>
              <div>
                <dt>Review after</dt>
                <dd>
                  <Time iso={edge.validity.review_after} />
                </dd>
              </div>
            </>
          ) : (
            <div>
              <dt>Validity window</dt>
              <dd>None. Only a contextual learning carries review dates.</dd>
            </div>
          )}
          {edge.learning_status ? (
            <div>
              <dt>What was learned</dt>
              <dd>{LEARNING_STATUS_LABELS[edge.learning_status]}</dd>
            </div>
          ) : null}
        </dl>
      </Section>

      <Section title="What else could explain it" name="alternatives">
        <Notes title="Possible confounders" notes={edge.confounders} empty="None recorded." />
        <Notes
          title="Other explanations"
          notes={edge.alternative_explanations}
          empty="None recorded."
        />
        <h5 className={styles.subhead}>Competing links</h5>
        {rivals.length === 0 ? (
          <p className={styles.empty}>None recorded.</p>
        ) : (
          <ul className={styles.items}>
            {rivals.map((ref) => (
              <li key={ref.id}>
                <Link target={ref} onGo={go} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Replaced and replacing" name="supersession">
        <dl className={styles.pairs}>
          <div>
            <dt>It replaced</dt>
            <dd>
              {supersession.replaces ? (
                <Link target={supersession.replaces} onGo={go} />
              ) : (
                "No earlier link."
              )}
            </dd>
          </div>
          <div>
            <dt>Replaced by</dt>
            <dd>
              {supersession.replacedBy.length > 0 ? (
                <ul className={styles.items}>
                  {supersession.replacedBy.map((e) => (
                    <li key={e.edge_id}>
                      <Link target={{ id: e.edge_id, edge: e }} onGo={go} />
                    </li>
                  ))}
                </ul>
              ) : edge.status === "SUPERSEDED" ? (
                "The link that replaced it is not on this map."
              ) : (
                "Not replaced."
              )}
            </dd>
          </div>
        </dl>
      </Section>

      <Section title="How Serene came to hold it" name="lineage">
        <dl className={styles.pairs}>
          <div>
            <dt>Proposed by</dt>
            <dd>{ACTOR_LABELS[provenance.created_by.kind]}</dd>
          </div>
          <div>
            <dt>How</dt>
            <dd>{METHOD_LABELS[provenance.method]}</dd>
          </div>
          {provenance.model ? (
            <div>
              <dt>Model</dt>
              <dd>
                {provenance.model.provider} {provenance.model.model_id}, prompt{" "}
                {provenance.model.prompt_version}
              </dd>
            </div>
          ) : null}
          <div>
            <dt>Recorded</dt>
            <dd>
              <Time iso={provenance.created_at} />
            </dd>
          </div>
          <div>
            <dt>Checked</dt>
            <dd>{VERIFICATION_LABELS[provenance.verification_status]}</dd>
          </div>
        </dl>

        <ol className={styles.chain} aria-label="Evidence trail, from this link down to raw evidence">
          <li className={styles.rung}>
            <h5 className={styles.subhead}>This link</h5>
            <Entry id={edge.edge_id} label={KIND_LABELS.hypothesis} />
          </li>
          <li className={styles.rung}>
            <h5 className={styles.subhead}>Derived from</h5>
            <List
              items={lineage.parents}
              keyOf={(ref) => ref.id}
              render={(ref) => <Link target={ref} onGo={go} />}
            />
            {lineage.parents.some((ref) => entityKind(ref.id) !== "evidence") ? (
              <p className={styles.aside}>
                The steps between these and the raw evidence are kept in Serene’s record but are
                not included in the map.
              </p>
            ) : null}
          </li>
          <li className={styles.rung}>
            <h5 className={styles.subhead}>Raw evidence it rests on</h5>
            <List
              items={lineage.raw}
              render={(r) => (
                <Entry
                  id={r.id}
                  label={KIND_LABELS.evidence}
                  note={r.declared ? "Also listed as this link’s source" : undefined}
                />
              )}
              keyOf={(r) => r.id}
            />
            {lineage.unreached.length > 0 ? (
              <>
                <h5 className={styles.subhead}>Cited, but not reached by the trail</h5>
                <Ids ids={lineage.unreached} label={KIND_LABELS.evidence} empty="" />
              </>
            ) : null}
          </li>
        </ol>
      </Section>

      <Section title="Not shown here" name="limits">
        <p>The map Serene sends does not include:</p>
        <ul className={styles.limits}>
          {NOT_IN_TWIN.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Section({
  title,
  name,
  headingRef,
  children,
}: {
  title: string;
  name: string;
  headingRef?: Ref<HTMLHeadingElement>;
  children: ReactNode;
}) {
  const id = useId();
  return (
    <section className={styles.section} aria-labelledby={id} data-section={name}>
      <h4 id={id} ref={headingRef} tabIndex={headingRef ? -1 : undefined} className={styles.heading}>
        {title}
      </h4>
      {children}
    </section>
  );
}

function Evidence({ items, empty }: { items: EvidenceItem[]; empty: string }) {
  if (items.length === 0) return <p className={styles.empty}>{empty}</p>;
  return (
    <List
      items={items}
      keyOf={(item) => item.id}
      render={(item) => <Entry id={item.id} label={ROLE_LABELS[item.role]} role={item.role} />}
    />
  );
}

function Ids({ ids, label, empty }: { ids: readonly string[]; label: string; empty: string }) {
  if (ids.length === 0) return <p className={styles.empty}>{empty}</p>;
  return <List items={ids} keyOf={(id) => id} render={(id) => <Entry id={id} label={label} />} />;
}

function Notes({ title, notes, empty }: { title: string; notes: readonly string[]; empty: string }) {
  return (
    <>
      <h5 className={styles.subhead}>{title}</h5>
      {notes.length === 0 ? (
        <p className={styles.empty}>{empty}</p>
      ) : (
        <ul className={styles.notes}>
          {notes.map((note, i) => (
            <li key={i}>{note}</li>
          ))}
        </ul>
      )}
    </>
  );
}

function List<T>({
  items,
  render,
  keyOf,
}: {
  items: readonly T[];
  render: (item: T) => ReactNode;
  keyOf: (item: T) => string;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const shown = open ? items : items.slice(0, SHOWN);
  return (
    <>
      <ul id={listId} className={styles.items}>
        {shown.map((item) => (
          <li key={keyOf(item)}>{render(item)}</li>
        ))}
      </ul>
      {items.length > SHOWN ? (
        <button
          type="button"
          className={styles.more}
          aria-expanded={open}
          aria-controls={listId}
          onClick={() => setOpen(!open)}
        >
          {open ? "Show fewer" : `Show all ${items.length}`}
        </button>
      ) : null}
    </>
  );
}

/** One recorded item: what it is, in words, and its id. */
function Entry({ id, label, note, role }: { id: string; label: string; note?: string; role?: string }) {
  return (
    <span className={styles.ref} data-entity-id={id} data-role={role}>
      <span className={styles.refLabel}>{label}</span>
      <code className={styles.refId}>{id}</code>
      {note ? <span className={styles.refNote}>{note}</span> : null}
    </span>
  );
}

/** An id that may be another link: chosen in place if it is on this map, otherwise just named. */
function Link({ target, onGo }: { target: LinkRef; onGo: (edgeId: string) => void }) {
  if (!target.edge) {
    const kind = entityKind(target.id);
    return (
      <Entry id={target.id} label={KIND_LABELS[kind]} note={kind === "hypothesis" ? "Not on this map" : undefined} />
    );
  }
  const meta = CATEGORIES[categorize(target.edge)];
  return (
    <button
      type="button"
      className={styles.link}
      data-edge-ref={target.id}
      data-category={categorize(target.edge)}
      onClick={() => onGo(target.id)}
    >
      <span className={styles.linkState}>
        <LineMark certainty={meta.certainty} className={styles.linkMark} />
        {meta.term}
      </span>
      <span className={styles.linkText}>{target.edge.relationship}</span>
      <code className={styles.refId}>{target.id}</code>
    </button>
  );
}

function Time({ iso }: { iso: string }) {
  return <time dateTime={iso}>{formatDate(iso)}</time>;
}
