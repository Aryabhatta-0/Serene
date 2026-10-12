"use client";

import { useEffect, useRef } from "react";
import { variableLabel } from "@/lib/causal-twin/categories";
import type { CausalEdge, CausalTwin } from "@/lib/causal-twin/model";
import {
  ACTOR_LABELS,
  KIND_LABELS,
  LEARNING_STATUS_LABELS,
  LEVEL_NAMES,
  METHOD_LABELS,
  NOT_IN_TWIN,
  VERIFICATION_LABELS,
  againstFor,
  competingLinks,
  entityKind,
  lineageOf,
  supersessionOf,
  supportFor,
  verdictReason,
} from "@/lib/causal-twin/provenance";
import type { TwinProvenance } from "@/lib/causal-twin/provenance-model";
import { FullProvenance } from "./FullProvenance";
import { Entry, Evidence, Ids, Link, List, Notes, Section, Time } from "./ProvenanceParts";
import styles from "./EdgeProvenance.module.css";

type EdgeProvenanceProps = {
  edge: CausalEdge;
  twin: CausalTwin;
  /** The provenance projection (#75) for this twin, when the source sent one. */
  provenance?: TwinProvenance | null;
  /** Choose another link (a rival, a replacement) without leaving the panel. */
  onSelectEdge: (edgeId: string) => void;
};

// Why Serene holds the selected link the way it does (Issue #39): the
// verdict, the evidence on each side, the experiments, where and when it
// holds, what else could explain it, what it replaced, and the chain down to
// raw evidence. Every item is a recorded id, labelled by what it is; nothing
// is scored, summarised away or made up.
//
// With the provenance projection (#75) the panel shows the complete chain:
// what each item says, when, where its evidence came from, every experiment
// and outcome, and every step down to raw evidence. Without it, only what the
// twin carries is shown and the panel says what it cannot show.
export function EdgeProvenance({ edge, twin, provenance: projection, onSelectEdge }: EdgeProvenanceProps) {
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

  const detail = projection?.edges.get(edge.edge_id) ?? null;
  if (projection && detail) {
    return (
      <FullProvenance
        edge={edge}
        twin={twin}
        detail={detail}
        provenance={projection}
        headingRef={headingRef}
        onSelectEdge={go}
      />
    );
  }

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
