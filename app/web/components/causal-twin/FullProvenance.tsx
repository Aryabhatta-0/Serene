"use client";

import type { Ref } from "react";
import { variableLabel } from "@/lib/causal-twin/categories";
import {
  EVIDENCE_KIND_LABELS,
  EXPERIMENT_STATUS_LABELS,
  LIFECYCLE_LABELS,
  NODE_KIND_LABELS,
  NOT_IN_PROJECTION,
  ORIGIN_LABELS,
  RESULT_LABELS,
  SOURCE_KIND_LABELS,
  anchorOf,
  chainOf,
  type ChainEntry,
} from "@/lib/causal-twin/chain";
import type { CausalEdge, CausalTwin } from "@/lib/causal-twin/model";
import {
  ACTOR_LABELS,
  LEARNING_STATUS_LABELS,
  LEVEL_NAMES,
  METHOD_LABELS,
  VERIFICATION_LABELS,
  competingLinks,
  verdictReason,
  type LinkRef,
} from "@/lib/causal-twin/provenance";
import type {
  EdgeProvenance,
  ExperimentProvenance,
  NodeOrigin,
  ProvenanceNode,
  TwinProvenance,
} from "@/lib/causal-twin/provenance-model";
import { Link, List, Notes, Section, Time } from "./ProvenanceParts";
import styles from "./EdgeProvenance.module.css";

type FullProvenanceProps = {
  edge: CausalEdge;
  twin: CausalTwin;
  detail: EdgeProvenance;
  provenance: TwinProvenance;
  headingRef: Ref<HTMLHeadingElement>;
  onSelectEdge: (edgeId: string) => void;
};

const STATUS_LABELS: Record<CausalEdge["status"], string> = {
  CANDIDATE: "Not established",
  SUPPORTED: "Supported by an experiment",
  REFUTED: "Refuted",
  SUPERSEDED: "Replaced",
};

// The panel with the provenance projection (#75): every dimension of #39,
// read from what the kernel sent, down to raw evidence. A node the kernel
// could not find is shown as a missing provenance node, never filled in.
export function FullProvenance({ edge, twin, detail, provenance, headingRef, onSelectEdge }: FullProvenanceProps) {
  const chain = chainOf(detail, provenance);
  const ref = (id: string): LinkRef => ({ id, edge: twin.edges.find((e) => e.edge_id === id) ?? null });
  const rivals = competingLinks(edge, twin);
  const learning = detail.learning;

  return (
    <div className={styles.provenance} data-provenance-for={edge.edge_id} data-provenance="full">
      <Section title="Why it is drawn this way" headingRef={headingRef} name="verdict">
        <p>{verdictReason(edge)}</p>
        <dl className={styles.pairs}>
          <div>
            <dt>Evidence ladder</dt>
            <dd data-field="level">
              Level {detail.epistemic_level} of 5: {LEVEL_NAMES[detail.epistemic_level]}
            </dd>
          </div>
          <div>
            <dt>State</dt>
            <dd data-field="state">
              {STATUS_LABELS[detail.status]} · {LIFECYCLE_LABELS[detail.lifecycle]}
            </dd>
          </div>
          <div>
            <dt>Link checked</dt>
            <dd data-field="verification">{VERIFICATION_LABELS[detail.verification_status]}</dd>
          </div>
          <div>
            <dt>Chain to raw evidence</dt>
            <dd data-field="complete">
              {chain.complete
                ? `Complete: rests on ${detail.lineage.raw_evidence.length} raw evidence`
                : `Incomplete: ${chain.missing.length} missing provenance node${chain.missing.length === 1 ? "" : "s"}`}
            </dd>
          </div>
        </dl>
      </Section>

      <Section title="Evidence for it" name="support">
        {detail.support.length === 0 ? (
          <p className={styles.empty}>Nothing recorded supports it yet.</p>
        ) : (
          <List
            items={detail.support}
            keyOf={(s) => s.entity_id}
            render={(s) => (
              <Cited
                id={s.entity_id}
                provenance={provenance}
                role={s.kind === "EXPERIMENTAL" ? "Experiment outcome: supports it" : "Observed with it"}
              />
            )}
          />
        )}
      </Section>

      <Section title="Evidence against it" name="against">
        {detail.counterevidence.length === 0 ? (
          <p className={styles.empty}>Nothing recorded counts against it.</p>
        ) : (
          <List
            items={[...detail.counterevidence].sort((a, b) => Number(b.contradicting_outcome) - Number(a.contradicting_outcome))}
            keyOf={(c) => c.entity_id}
            render={(c) => (
              <Cited
                id={c.entity_id}
                provenance={provenance}
                against
                role={c.contradicting_outcome ? "Experiment outcome: contradicts it" : "Counts against it"}
              />
            )}
          />
        )}
      </Section>

      <Section title="Experiments" name="experiments">
        {detail.experiments.length === 0 ? (
          <p className={styles.empty}>No experiment has been set up for this link.</p>
        ) : (
          <ul className={styles.items}>
            {detail.experiments.map((x) => (
              <li key={x.experiment_id}>
                <Experiment experiment={x} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Where and when it holds" name="scope">
        <dl className={styles.pairs}>
          <div>
            <dt>Situations</dt>
            <dd data-field="scope">{detail.scope_contexts.map(variableLabel).join(", ")}</dd>
          </div>
          {detail.validity ? (
            <>
              <div>
                <dt>Valid from</dt>
                <dd data-field="valid-from">
                  <Time iso={detail.validity.valid_from} />
                </dd>
              </div>
              <div>
                <dt>Review after</dt>
                <dd data-field="review-after">
                  <Time iso={detail.validity.review_after} />
                </dd>
              </div>
            </>
          ) : (
            <div>
              <dt>Validity window</dt>
              <dd>None. Only a contextual learning carries review dates.</dd>
            </div>
          )}
        </dl>
        {learning ? (
          <div data-learning={learning.learning_id}>
            <h5 className={styles.subhead}>What was learned</h5>
            <p>{learning.statement}</p>
            <dl className={styles.pairs}>
              <div>
                <dt>Status now</dt>
                <dd data-field="learning-status">
                  {LEARNING_STATUS_LABELS[learning.effective_status]}
                  {learning.effective_status !== learning.recorded_status
                    ? ` (recorded as ${LEARNING_STATUS_LABELS[learning.recorded_status].toLowerCase()})`
                    : ""}
                </dd>
              </div>
              <div>
                <dt>Review</dt>
                <dd data-field="review-status">
                  {learning.review_due ? "Due now: " : "Next due "}
                  <Time iso={learning.review_after} />, with {ACTOR_LABELS[learning.reviewer_kind].toLowerCase()}
                </dd>
              </div>
              <div>
                <dt>Holds in</dt>
                <dd>{learning.scope_contexts.map(variableLabel).join(", ")}</dd>
              </div>
              {learning.status_changed_at ? (
                <div>
                  <dt>Status last set</dt>
                  <dd>
                    <Time iso={learning.status_changed_at} />
                  </dd>
                </div>
              ) : null}
              <div>
                <dt>From experiments</dt>
                <dd>
                  <IdLinks ids={learning.experiment_ids} />
                </dd>
              </div>
              <div>
                <dt>From outcomes</dt>
                <dd>
                  <IdLinks ids={learning.outcome_ids} />
                </dd>
              </div>
              <div>
                <dt>Counterevidence</dt>
                <dd>{learning.counterevidence.length === 0 ? "None recorded." : <IdLinks ids={learning.counterevidence} />}</dd>
              </div>
              {learning.superseded_learnings.length > 0 ? (
                <div>
                  <dt>Earlier learnings it replaced</dt>
                  <dd>{learning.superseded_learnings.join(", ")}</dd>
                </div>
              ) : null}
            </dl>
            <Notes title="Would need a retest if" notes={learning.retest_triggers} empty="None recorded." />
          </div>
        ) : null}
      </Section>

      <Section title="What else could explain it" name="alternatives">
        <Notes title="Possible confounders" notes={detail.confounders} empty="None recorded." />
        <Notes title="Other explanations" notes={detail.alternative_explanations} empty="None recorded." />
        <h5 className={styles.subhead}>Competing links</h5>
        {rivals.length === 0 ? (
          <p className={styles.empty}>None recorded.</p>
        ) : (
          <ul className={styles.items}>
            {rivals.map((r) => (
              <li key={r.id}>
                <Link target={r} onGo={onSelectEdge} />
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Replaced and refuted" name="supersession">
        <dl className={styles.pairs}>
          <div>
            <dt>Replaced by</dt>
            <dd data-field="superseded-by">
              {detail.supersession.superseded_by ? (
                <Link target={ref(detail.supersession.superseded_by)} onGo={onSelectEdge} />
              ) : (
                "Not replaced."
              )}
            </dd>
          </div>
          {detail.supersession.reason ? (
            <div>
              <dt>Why it was replaced</dt>
              <dd data-field="supersession-reason">{detail.supersession.reason}</dd>
            </div>
          ) : null}
          <div>
            <dt>It replaced</dt>
            <dd>
              {detail.supersession.supersedes ? (
                <Link target={ref(detail.supersession.supersedes)} onGo={onSelectEdge} />
              ) : (
                "No earlier link."
              )}
            </dd>
          </div>
          <div>
            <dt>Refuted</dt>
            <dd data-field="refutation">
              {detail.refutation ? (
                <>
                  <span>Reasons: {detail.refutation.reason_codes.join(", ")}</span>
                  <br />
                  <span>
                    By outcome: <IdLinks ids={detail.refutation.outcome_ids} />
                  </span>
                </>
              ) : (
                "Not refuted."
              )}
            </dd>
          </div>
        </dl>
      </Section>

      <Section title="How Serene came to hold it" name="lineage">
        <Origin origin={detail.origin} />
        <h5 className={styles.subhead}>Every step, from this link down to raw evidence</h5>
        <ol className={styles.chain} aria-label="Evidence trail, from this link down to raw evidence" data-chain="lineage">
          {chain.lineage.map((e) => (
            <li key={e.id} className={styles.rung} data-depth={e.depth}>
              <Step entry={e} />
            </li>
          ))}
        </ol>
        {chain.alsoCited.length > 0 ? (
          <>
            <h5 className={styles.subhead}>Also behind this link: experiments, outcomes and their evidence</h5>
            <ol className={styles.chain} aria-label="Other items this link cites, with their evidence" data-chain="cited">
              {chain.alsoCited.map((e) => (
                <li key={e.id} className={styles.rung}>
                  <Step entry={e} />
                </li>
              ))}
            </ol>
          </>
        ) : null}
      </Section>

      <Section title="Not shown here" name="limits">
        <p>Kept private, so not shown:</p>
        <ul className={styles.limits}>
          {NOT_IN_PROJECTION.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

/** An item the link cites: what it says, when, where its evidence came from, and a link to its chain. */
function Cited({ id, provenance, role, against }: { id: string; provenance: TwinProvenance; role: string; against?: boolean }) {
  const node = provenance.nodes.get(id);
  if (!node) return <MissingEntry id={id} provenance={provenance} />;
  return (
    <span className={styles.ref} data-entity-id={id} data-role={against ? "evidence-against" : undefined} data-origin={node.evidence_origin}>
      <span className={styles.refLabel}>{role}</span>
      <span>{node.summary}</span>
      <span className={styles.refNote}>
        {NODE_KIND_LABELS[node.kind]} · <Time iso={node.occurred_at} /> · {ORIGIN_LABELS[node.evidence_origin]} ·{" "}
        {VERIFICATION_LABELS[node.verification_status]}
      </span>
      <a href={`#${anchorOf(id)}`} data-provenance-link={id} className={styles.refId}>
        {id}
      </a>
    </span>
  );
}

function Experiment({ experiment: x }: { experiment: ExperimentProvenance }) {
  return (
    <div className={styles.ref} data-experiment-id={x.experiment_id}>
      <span className={styles.refLabel}>Experiment · {EXPERIMENT_STATUS_LABELS[x.status]}</span>
      <span>{x.intervention}</span>
      <span className={styles.refNote}>
        Measured by: {x.outcome_measure}
        {x.safety_class ? ` · Safety class ${x.safety_class}` : ""}
        {x.started_at ? (
          <>
            {" "}· Started <Time iso={x.started_at} />
          </>
        ) : null}
        {x.ended_at ? (
          <>
            {" "}· Ended <Time iso={x.ended_at} />
          </>
        ) : null}
      </span>
      <a href={`#${anchorOf(x.experiment_id)}`} data-provenance-link={x.experiment_id} className={styles.refId}>
        {x.experiment_id}
      </a>
      <h5 className={styles.subhead}>Outcomes</h5>
      {x.outcomes.length === 0 ? (
        <p className={styles.empty}>No outcome recorded yet.</p>
      ) : (
        <ul className={styles.items}>
          {x.outcomes.map((o) => (
            <li key={o.outcome_id} data-outcome-id={o.outcome_id} data-from-experiment={o.experiment_id}>
              <span className={styles.ref}>
                <span className={styles.refLabel}>Outcome: {RESULT_LABELS[o.result]}</span>
                <span>{o.summary}</span>
                <span className={styles.refNote}>
                  Reported <Time iso={o.reported_at} /> · from experiment <code>{o.experiment_id}</code>
                </span>
                <a href={`#${anchorOf(o.outcome_id)}`} data-provenance-link={o.outcome_id} className={styles.refId}>
                  {o.outcome_id}
                </a>
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Origin({ origin }: { origin: NodeOrigin }) {
  return (
    <dl className={styles.pairs}>
      <div>
        <dt>Proposed by</dt>
        <dd>{ACTOR_LABELS[origin.actor_kind]}</dd>
      </div>
      <div>
        <dt>How</dt>
        <dd>{METHOD_LABELS[origin.method]}</dd>
      </div>
      {origin.model ? (
        <div>
          <dt>Model</dt>
          <dd>
            {origin.model.provider} {origin.model.model_id}, prompt {origin.model.prompt_version}
          </dd>
        </div>
      ) : null}
      <div>
        <dt>Recorded</dt>
        <dd>
          <Time iso={origin.created_at} />
        </dd>
      </div>
    </dl>
  );
}

/** One node on a chain, with an anchor so links to it land here. */
function Step({ entry }: { entry: ChainEntry }) {
  if (!entry.node) {
    return (
      <div id={anchorOf(entry.id)} data-missing-node={entry.id}>
        <h5 className={styles.subhead}>Missing provenance node</h5>
        <p className={styles.aside}>
          Serene’s record does not hold this item, so nothing about it can be shown. Named by{" "}
          {entry.missing.referenced_by.join(", ") || "this link"}.
        </p>
        <code className={styles.refId}>{entry.id}</code>
      </div>
    );
  }
  const node: ProvenanceNode = entry.node;
  return (
    <div id={anchorOf(node.entity_id)} data-node-id={node.entity_id} data-node-kind={node.kind}>
      <h5 className={styles.subhead}>
        {NODE_KIND_LABELS[node.kind]}
        {node.epistemic_level !== null ? ` · level ${node.epistemic_level}` : ""} ·{" "}
        {VERIFICATION_LABELS[node.verification_status]}
        {node.lifecycle !== "ACTIVE" ? ` · ${LIFECYCLE_LABELS[node.lifecycle]}` : ""}
      </h5>
      <p>{node.summary}</p>
      <p className={styles.aside}>
        <Time iso={node.occurred_at} /> · {ORIGIN_LABELS[node.evidence_origin]} · {METHOD_LABELS[node.origin.method]} by{" "}
        {ACTOR_LABELS[node.origin.actor_kind].toLowerCase()}
      </p>
      {node.evidence ? (
        <p className={styles.aside} data-evidence-detail={node.evidence.external ? "external" : "family"}>
          {EVIDENCE_KIND_LABELS[node.evidence.evidence_kind]} via {SOURCE_KIND_LABELS[node.evidence.source_kind]}
          {node.evidence.external ? ` · outside source${node.evidence.source_host ? `: ${node.evidence.source_host}` : ""}` : " · family source"}
          {node.evidence.checks_passed.length > 0 ? ` · checks passed: ${node.evidence.checks_passed.join(", ")}` : ""}
          {node.evidence.rejection_reason_codes.length > 0
            ? ` · rejected: ${node.evidence.rejection_reason_codes.join(", ")}`
            : ""}{" "}
          · fingerprint <code>{node.evidence.content_digest.slice(0, 12)}</code>
        </p>
      ) : null}
      {node.parents.length > 0 ? (
        <p className={styles.aside}>
          Derived from: <IdLinks ids={node.parents} />
        </p>
      ) : null}
      {node.superseded_by ? (
        <p className={styles.aside}>
          Replaced by <code>{node.superseded_by}</code>
        </p>
      ) : null}
      <code className={styles.refId}>{node.entity_id}</code>
    </div>
  );
}

function MissingEntry({ id, provenance }: { id: string; provenance: TwinProvenance }) {
  const gap = provenance.missing.get(id);
  return (
    <span className={styles.ref} data-entity-id={id} data-missing-node={id}>
      <span className={styles.refLabel}>Missing provenance node</span>
      <span className={styles.refNote}>Named by {gap?.referenced_by.join(", ") ?? "this link"}; not in Serene’s record.</span>
      <a href={`#${anchorOf(id)}`} data-provenance-link={id} className={styles.refId}>
        {id}
      </a>
    </span>
  );
}

function IdLinks({ ids }: { ids: readonly string[] }) {
  return (
    <>
      {ids.map((id, i) => (
        <span key={id}>
          {i > 0 ? ", " : ""}
          <a href={`#${anchorOf(id)}`} data-provenance-link={id}>
            <code>{id}</code>
          </a>
        </span>
      ))}
    </>
  );
}
