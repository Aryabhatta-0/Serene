# Serene economics — issue #55

This is a synthetic operating budget, not a measured forecast or a pricing
decision. `LLM proposes; deterministic policy decides` is unchanged. cfo.ai is
an engineering analysis workspace; it cannot write runtime policy, authorize an
acquisition, change browser bounds or reduce verifier requirements.

## Inputs and provenance

[inputs.json](economics/inputs.json) records each input's **name, unit, source,
integer value and measured/assumed basis**. All 36 baseline/alternative inputs
are **assumed**. Rates inherited from the earlier local scaffold are identified
as local estimates, not provider billing. The additional storage, memory-read
and telemetry amounts are synthetic budgets. Zero incremental usage is an
explicit assumption, not an unknown price treated as zero.

| Driver | Assumed rate (micro-USD) | Base usage/family-month | Optional parent confirmation |
| --- | ---: | ---: | ---: |
| LLM/model, blended input/output | 6,000 / 1,000 tokens | 400,000 tokens | 1,500 tokens |
| Browser/evidence acquisition | 20,000 / session | 6 sessions | 0 |
| Database writes | 2 / write | 3,000 | 4 |
| Database reads | 1 / read | 60,000 | 30 |
| Storage | 20,000 / GB-month | 1 GB-month | 0 |
| Memory writes | 50 / commit | 60 | 0 |
| Memory reads | 1 / lookup | 600 | 0 |
| Verification overhead | 100 / incremental check | 12 | 0 |
| Telemetry/logging | 500 / 1,000 events | 12,000 | 0 |

The alternative caregiver confirmation assumes 2,400 LLM tokens, six database
writes and 40 reads; other incremental quantities remain zero. The plan assumes
12 optional confirmations/family-month, 12,000,000 micro-USD subscription revenue
per family-month, 400 families, 18,000,000,000 micro-USD fixed cost/month, and
250,000,000,000 micro-USD cash. These are planning inputs, not actual subscriptions,
customers, payroll or bank balances.

Sensitivity assumptions have the same explicit provenance:

| Name | Value | Unit | Basis | Source |
| --- | ---: | --- | --- | --- |
| sensitivity.low_subscription | 8,000,000 | micro-USD/family-month | assumed | #55 synthetic downside case |
| sensitivity.high_subscription | 16,000,000 | micro-USD/family-month | assumed | #55 synthetic upside case |
| sensitivity.llm_usage_bps | 20,000 | basis points of baseline token usage | assumed | #55 synthetic doubled-usage case |

**Measured context, excluded from the forecast:** the existing
[NeatLogs-linked report](live-eval-2026-10-11.md) records 988,176 tokens across six
synthetic Serene runs (`serene-live3`, commit `89e41cd`). Its provider did **not**
report monetary spend. The token total is a historical run measurement, not
monthly usage per family, and is not multiplied into this budget. The earlier
[report](live-eval-2026-10-10.md) also distinguishes measured tokens from unreported
cost. No live evaluation, private traces, account billing or provider price
lookup was needed or used.

## Formulas and reproducible results

Money is integer micro-USD (1 USD = 1,000,000 micro-USD). One basis point is
1/10,000 of a ratio. Unit conversion denominators (e.g. 1,000 tokens) and 30-day
months are explicit calculation conventions.
The `days_per_month` convention is registered as an assumed input: 30 day/month,
source `issue-55 planning convention; constant monthly burn converted using
30-day months`. It is populated as an additional row in the same cfo.ai table.

For each driver `d`, with base quantity `b`, per-acquisition quantity `a`, monthly
acquisitions `n`, rate `r` and rate denominator `u`:

```text
monthly_quantity[d] = b[d] + n * a[d]
monthly_driver_cost[d] = ceil(monthly_quantity[d] * r[d] / u[d])
monthly_cost_per_family = sum(monthly_driver_cost[d])
standalone_acquisition_estimate = sum(ceil(a[d] * r[d] / u[d]))
gross_margin_bps = floor((subscription - monthly_cost_per_family) * 10000 / subscription)
monthly_variable_cost = families * monthly_cost_per_family
monthly_revenue = families * subscription
monthly_burn = fixed_cost + monthly_variable_cost - monthly_revenue
runway_days = floor(cash * days_per_month / monthly_burn)
```

Ceil division is `(numerator + denominator - 1) // denominator` in Python.
Monthly quantities are aggregated before rounding; independently rounded
standalone requests need not sum exactly to a monthly bill. Zero revenue has
undefined margin (`None`); nonpositive burn has no finite runway (`None`). Zero
cash with positive burn gives zero days. Negative quantities/prices, booleans
and fractional input money are rejected. Sensitivity rounds scaled quantities
up and never mutates baseline inputs.

The synthetic baseline yields **2,725,256 micro-USD ($2.725256) per family-month**,
**7,728 bps (77.28%) gross margin**, 1,090,102,400 micro-USD monthly variable cost,
4,800,000,000 micro-USD monthly revenue, 14,290,102,400 micro-USD monthly burn and
**524 days** of runway. LLM usage contributes 2,508,000 micro-USD/family-month,
about 92.02% of variable cost; browser sessions contribute 120,000, and database
reads 60,360. Those are the largest modeled drivers.

| Synthetic case | Cost/family-month | Gross margin (floored bps) |
| --- | ---: | ---: |
| Baseline: $12 assumed revenue | $2.725256 | 77.28% |
| $8 assumed revenue | $2.725256 | 65.93% |
| Twice the assumed LLM token usage, $12 revenue | $5.233256 | 56.38% |
| $16 assumed revenue | $2.725256 | 82.96% |

## Genuine cfo.ai analysis

Exactly one Scenario was created: **Serene economics #55 - assumed operating
case**, reference `Serene economics #55 - assumed operating case#fb5`.
The existing remote MCP at `https://api.cfo.ai/mcp` was used with the user's
authenticated Codex OAuth session. Scenario creation changelog: **282907**;
assumption-register page: **282930**; 70-row modeled table: **282944**.
The Scenario's variables are isolated from Main. It was not merged.

[cfo-model-request.json](economics/cfo-model-request.json) is the exact non-secret
table creation request: it populates assumptions, unit conversions, component
costs, baseline results, the optional acquisition comparison and sensitivity
formulas. [cfo-evidence.json](economics/cfo-evidence.json) records the Scenario,
receipts and request hash. [cfo-readback.json](economics/cfo-readback.json) retains
the inspected calculated rows from cfo.ai, including costs/family, margin,
drivers, burn/runway and sensitivity. It contains only this synthetic model;
credentials, account/user identities and unrelated workspace data are excluded.
The separate [convention request](economics/cfo-convention-request.json) adds the
named 30-day assumption and references it in runway; the final table has 71 rows.

cfo.ai uses its own numeric engine (reported as FLOAT); it is analysis evidence,
not an authority calculation. The reviewed Python model uses integer arithmetic.
Saved cfo.ai output is compared mechanically with the integer fixture. No cfo.ai
response is represented as measured provider pricing.

## The one constrained decision

`pickup_confirmation_decision` in `serene/adapters/cfoai.py` compares **only an
optional pickup-cutoff confirmation from the parent versus an already authorized
caregiver**. Before calling it, trusted policy must establish that both observers
can provide the same first-hand schedule observation with identical predictions,
evidence requirements, admissibility and expected uncertainty reduction. A
caregiver's behavioral report is not interchangeable with a parent's report;
disagreement remains separate evidence.

The helper requires an explicit set of policy-eligible options and a required
parent-question flag. If a parent question is required, the caregiver is excluded;
if the parent is ineligible, no substitute is chosen. It grants no authorization
and sends no messages. It is a reviewed, scoped helper, not a globally enabled
runtime price table or a second planner. Default investigation assembly continues
to use unknown costs unless a trusted caller supplies a cost model.

The economics inputs estimate **9,038 micro-USD** for the parent option and
**14,452 micro-USD** for the caregiver option. Only after certified equivalence
does deterministic policy prefer the parent, saving an assumed **64,968
micro-USD ($0.064968) per family-month** at 12 confirmations.

`serene/policies/acquisition.py` first removes unsafe and policy-ineligible
options, prioritizes safety, required parent questions, evidence quality and
ordinal information value, and forms the top class without using price. Cost
can reorder it only if the entire class has a matching, nonempty, trusted
equivalence key. Required parent questions disable cost ordering. Equal prices
and two unknown prices use stable identifiers and are not labeled cost decisive.
Unknown/invalid/failing estimates stay unknown; estimates are snapshotted once.

The existing `MinimumDataPolicy` is also tightened conservatively: cost ordering
requires an identical complete evidence request (fields, acquisition mode,
question, subject, domain bounds and hypothesis predictions), in addition to its
existing safety/need/value/burden/latency tie. Equal HIGH ordinals for different
observations do not suffice. No browser/verifier, admission or authorization rule
was weakened or bypassed. This is a guard on the existing architecture, not an
additional product decision.

## Safe structured evidence

The helper emits `policy.acquisition_cost` through existing `SafeTelemetry`:

- `task_id`: hashed candidate identifier;
- `decision`: hashed selected identifier, or `NONE`;
- `checks_passed`: `SAFETY_ELIGIBILITY_QUALITY_UNCERTAINTY_TIED` only for members of
  the certified top tie; otherwise `NOT_TIED`;
- `admitted`, `safety_class`, `source_kind`, `information_value`: policy criteria;
- `cost_known`, `cost_micro_usd`: integer estimate or literal `UNKNOWN`;
- `status`: `SELECTED`/`NOT_SELECTED`; `reason_codes`: decisive policy reason.

No child/family identifier, question, domain or equivalence text is logged.
Even token-like candidate identifiers are hashed. Sink failure cannot alter the
decision. Existing telemetry schema and NeatLogs adapter bytes are unchanged.
The safe trace is reproduced in [local-report.json](economics/local-report.json).

## Verification and limitations

```powershell
uv run pytest -q tests/test_economics.py tests/test_acquisition_costs.py tests/test_cfoai_economics.py tests/test_investigation.py tests/test_architecture_boundaries.py --junitxml=.venv/cfo55-focused.xml
uv run python scripts/economics_audit.py .venv/cfo55-focused.xml
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python scripts/economics_report.py --check
uv run python scripts/ledger_selfcheck.py
uv run python scripts/secret_scan.py
```

The issue's acceptance criteria and the additional safety/data requirements are
mapped to executable checks in [acceptance-audit.json](economics/acceptance-audit.json).
All fixtures are synthetic; tests make no cfo.ai or provider network calls.

Limitations: blended token prices omit provider-specific input/output/cache
pricing, subscription allocation, taxes, discounts, minimum commitments and
volume tiers. Retention and usage growth are not forecasts. Memory and verifier
rates represent incremental non-LLM overhead; generation tokens belong in LLM
usage, and general database I/O belongs in database counts to avoid double
counting. Telemetry excludes fixed service fees (include those in fixed burn).
Human labor, payment processing, support, fraud/refunds and acquisition spend
are not itemized; the fixed-cost allowance is not a validated breakdown. Higher
LLM retry usage could materially change costs. Runway assumes constant family
count, revenue and spend. Coarse ordinal information value is not a probability.
The equivalence key is a trusted-policy contract, not a planner-controlled field.

The old `SERENE_ECONOMICS_V1` API and its historical evaluation fixture are
retained unchanged for compatibility. They predate storage/telemetry budgeting;
use the provenance-bearing v2 inputs for this analysis. No evaluation artifact,
holdout/scorer/oracle, frontend file or Hermes internal was changed.
