---
domain: SecOps | FinOps | IaC
topic: <short title>
status: draft | ready
confidence: high | medium | low
whitepaper: WP2 | WP3 | none
---

# <Finding title>

## Rule
<A single, concrete, checkable statement.>

## Source
<Named, current authority — CIS Benchmark vX, AWS/GCP/Azure Well-Architected pillar, NIST, FinOps Foundation. Link + publication date. Note if it may be stale.>

## Gate mapping
- Engine: Checkov | tfsec | Infracost | (new check to build)
- Check ID / calculation: <e.g. CKV_AWS_20, or the Infracost line item>
- Severity in approval summary: critical | high | medium | low

## Expected cases (for the Tester's fixtures)
- **Known-bad** (must be flagged): <config snippet or description>
- **Known-good** (must pass): <config snippet or description>
- **Cost reference** (FinOps only): <reference figure + date + how derived, for reconciliation>

## Notes
<Rationale, caveats, anything the Developer or whitepaper author should know.>
