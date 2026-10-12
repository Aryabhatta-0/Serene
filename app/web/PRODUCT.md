# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Parents who want to understand what is happening with their child: a change
in behaviour, sleep, mood or routine that they cannot yet explain. Caregivers
may later be given narrow, parent-granted, expiring read access to one child.

## Product Purpose

Serene is a self-correcting, evidence-bound family intelligence agent. It
interprets conversations, identifies behavioural patterns, generates competing
hypotheses and verifies evidence before it recommends anything, and it can
always explain why it believes what it believes. Success is a parent who
understands their child better and trusts the reasoning because it is shown.

## Positioning

What happened, what Serene remembers and what it believes are kept apart.
Models propose; deterministic code holds authority over evidence validity,
safety, promotion and memory writes; the parent authorizes every intervention.

## Operating Context

Five primary surfaces: Today, Memory, Investigations, Experiments and Causal
Twin. Experiments are small, reversible N-of-1 changes that only start with
parent approval and are classified GREEN, AMBER or RED (RED fails closed).
Memory is long-term, reviewed before it is kept, and flags contradictions and
outdated information.

## Capabilities and Constraints

- Projection streaming over Supabase Realtime is implemented (#33). A parent
  connects to their child's record by signing in and choosing a child (#87):
  Today, Investigations and Experiments then read live projection state, and
  approval decisions go through the authenticated transport (#84). Memory
  (#99) and the Causal Twin (#75) stream too; the Twin reads a privacy-safe
  row with the complete provenance of every link. Every surface shows an honest
  empty state when nobody is signed in.
- Certainty is part of the product language: possibility, observed, tested in
  this family's context, and refuted (kept visible, never erased).
- No API keys, model providers or external services are needed to run the web
  shell.

## Brand Commitments

- Name: Serene (the repository is still named `morrow`).
- The bloom flower is the logo and favicon.

## Evidence on Hand

No real family data, testimonials, customers or metrics exist for the
interface. Tests and evaluation use synthetic data only. The UI must never
fabricate counts, dates, identifiers or family content.

## Product Principles

1. Child safety first; around safety and authorization, fail closed.
2. Reliable evidence before any claim, with provenance a parent can follow.
3. Transparency: every belief shows how firmly it is held and why.
4. Human authority over autonomous AI decisions.
5. A child's data belongs to the parent; access is explicit and scoped.

## Accessibility & Inclusion

Copy and type are chosen for legibility under stress (Atkinson Hyperlegible
Next is the reading face). Motion respects `prefers-reduced-motion`; keyboard
users can skip straight to content.
