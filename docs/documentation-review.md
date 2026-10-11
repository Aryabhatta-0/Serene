# Core documentation review (#60)

Scope: architecture, evidence model, safety, privacy and evaluation. Historical
eval reports and frozen artifacts are unchanged.

- [x] Implementation status names actual modules; obsolete branch A/B delivery claims removed.
- [x] Model proposals, deterministic admission/promotion/safety, independent verification,
  authenticated parent approval and single-writer memory are distinct authorities.
- [x] Experience, memory and belief have separate owners; telemetry never supplies authority.
- [x] Non-goals and excluded-technology rationale are explicit across the five documents.
- [x] The synthetic offline Maya integration is distinguished from live provider connectivity.
- [x] cfo.ai results are assumed economics, with genuine readback evidence, not measured bills.
- [x] Privacy gaps and missing required merge checks remain explicit (#59, #58).
- [x] Historical results remain failures/inconclusive/invalid as applicable; no controlled win claimed.
- [ ] Controlled-dev/1 final verdict reviewed; #53 assessed only after completion.
- [ ] Final link/reference check recorded after the evaluation section settles.

Reproduce the link check and verify referenced GitHub issues/PRs exist:

```bash
uv run python scripts/docs_check.py --github
uv run pytest -q tests/test_documentation.py
```

The GitHub option is read-only and requires the existing `gh` CLI. CI's local
link test needs no account, network or provider keys. It checks file targets;
external page availability and Markdown anchor semantics require manual review.
