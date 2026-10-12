import { LineMark, type Certainty } from "@/components/notation/LineMark";
import { ACTOR_LABELS, LEVEL_NAMES, METHOD_LABELS } from "@/lib/causal-twin/provenance";
import type { Patch, PatchStatus } from "@/lib/memory/model";
import { CHECK_LABELS, OPERATION_LABELS, STATUS_LABELS, anchor, proposedTitle } from "@/lib/memory/present";
import { Entries, Pair, Pairs, Reasons, Time } from "./parts";
import styles from "./Memory.module.css";

// Kept is drawn solid, refused struck through, and awaiting review dotted:
// the certainty notation, always next to the state in words.
const STATUS_MARK: Record<PatchStatus, Certainty> = {
  COMMITTED: "tested",
  REJECTED: "refuted",
  PROPOSED: "unknown",
};

type PatchCardProps = {
  patch: Patch;
  /** The memory this patch wrote, when it is still in memory. */
  memoryHref?: string;
  headingLevel?: "h4" | "h5";
};

// One proposed change to memory: what it would do, who proposed it and from
// what, what the fixed review found, and the outcome. A refused change always
// says why. Nothing here can approve, commit or edit it.
export function PatchCard({ patch, memoryHref, headingLevel: Heading = "h5" }: PatchCardProps) {
  const title = proposedTitle(patch);
  const { origin } = patch;
  return (
    <article
      id={anchor.patch(patch.patch_id)}
      className={styles.patch}
      data-patch-id={patch.patch_id}
      data-status={patch.status}
      aria-label={`${STATUS_LABELS[patch.status]}: ${title ?? patch.target_path}`}
    >
      <p className={styles.patchState}>
        <LineMark certainty={STATUS_MARK[patch.status]} className={styles.stateMark} />
        <span>{STATUS_LABELS[patch.status]}</span>
        <span className={styles.patchOperation}>{OPERATION_LABELS[patch.operation]}</span>
      </p>
      <Heading className={styles.patchTitle}>{title ?? patch.target_path}</Heading>
      <p className={styles.effect} data-effect={patch.status}>
        {patch.status === "COMMITTED"
          ? "Memory changed"
          : patch.status === "REJECTED"
            ? "Memory unchanged: the review refused it"
            : "Memory unchanged until the review decides"}
      </p>

      {patch.status === "REJECTED" ? (
        <div className={styles.refusal}>
          <p className={styles.subhead}>Why it was refused</p>
          <Reasons codes={patch.rejection_reasons} label="Reasons it was refused" tone="against" />
        </div>
      ) : null}

      <Pairs>
        <Pair term="Where">
          <code className={styles.refId}>{patch.target_path}</code>
        </Pair>
        <Pair term="Proposed by">
          {ACTOR_LABELS[origin.actor_kind]}
          {origin.model ? (
            <span className={styles.aside}>
              {" "}
              ({origin.model.provider} {origin.model.model_id}, prompt {origin.model.prompt_version})
            </span>
          ) : null}
        </Pair>
        <Pair term="How">{METHOD_LABELS[origin.method]}</Pair>
        <Pair term="Proposed">
          <Time iso={origin.created_at} />
        </Pair>
        <Pair term="Needs at least">
          Level {patch.required_level} of 5: {LEVEL_NAMES[patch.required_level]}
        </Pair>
        <Pair term="Review">
          {patch.review === null ? (
            "Not reviewed yet."
          ) : (
            <>
              {patch.review.passed ? "Passed" : "Did not pass"}
              {patch.review.checks_passed.length > 0 ? (
                <ul className={styles.checks} aria-label="Checks it passed">
                  {patch.review.checks_passed.map((check) => (
                    <li key={check}>{CHECK_LABELS[check]}</li>
                  ))}
                </ul>
              ) : null}
            </>
          )}
        </Pair>
        {patch.decided_at ? (
          <Pair term="Decided">
            <Time iso={patch.decided_at} />
          </Pair>
        ) : null}
        {patch.commit_sha ? (
          <Pair term="Written as">
            <code className={styles.refId} title={patch.commit_sha}>
              {patch.commit_sha.slice(0, 12)}
            </code>
            {memoryHref ? (
              <>
                {" "}
                <a href={memoryHref}>See the memory</a>
              </>
            ) : (
              <span className={styles.aside}> (since replaced in memory)</span>
            )}
          </Pair>
        ) : null}
      </Pairs>

      <p className={styles.subhead}>What it was drawn from</p>
      <Entries ids={origin.derived_from} empty="Nothing recorded." label="What it was drawn from" />
      <p className={styles.subhead}>Raw evidence it rests on</p>
      <Entries ids={origin.source_ids} empty="None recorded." label="Raw evidence it rests on" />

      <details className={styles.diff}>
        <summary>Show the proposed change</summary>
        <pre aria-label="The proposed change, line by line. Lines starting with + are added; lines starting with - are removed.">
          {patch.diff}
        </pre>
      </details>
    </article>
  );
}
