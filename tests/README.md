# tests/

The Tester's home. Above all, this is where **gate accuracy is proven**.

## Golden fixtures
For each rule in `research/findings/`, there must be:

- a **known-bad** fixture the security/cost gate **must** flag (a missed known-bad is the credibility killer), and
- a **known-good** fixture it **must** pass (false positives erode trust too).

For cost rules, assert the Infracost estimate reconciles against the Researcher's reference figure within an agreed tolerance.

A gate is not "done" until every fixture passes. Keep a coverage view: which rules have fixtures, which don't.

## Layers
- **Black-box** — drive the full narrative (intent → IaC → summary → approval → apply → manifest update) and confirm the synthesized summary matches the raw gate findings (no drift between what the human reads and what's true).
- **White-box** — manifest resolution, criticality transitivity through the dependency graph, rollback/snapshot triggers, manifest auto-update correctness, edge cases.

## Reporting
Keep a short, current test report (pass/fail + per-gate fixture coverage) the orchestrator can mirror to the command center.

## Suggested layout
```
tests/
  fixtures/
    security/   known-bad/  known-good/
    cost/       cases + reference figures
  black_box/
  white_box/
  REPORT.md     current pass/fail + coverage
```
