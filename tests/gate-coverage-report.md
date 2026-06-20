# Gate Coverage Report
**Date:** 2026-06-04  
**Tester:** Tester subagent (Claude Sonnet 4.6)  
**Checkov version:** 3.2.532  
**Status:** CLOSED — all acceptance criteria pass

---

## 1. Per-Rule Coverage Table

| Rule | Fixture (bad) | Fixture (good) | Expected bad | Actual bad | Expected good | Actual good | Result |
|---|---|---|---|---|---|---|---|
| CKV_AWS_24 | sec_sg_open_ingress_bad.tf | sec_sg_open_ingress_good.tf | FAILED | FAILED | PASSED | PASSED | PASS |
| CKV_AWS_16 | sec_rds_encryption_bad.tf | sec_rds_encryption_good.tf | FAILED | FAILED | PASSED | PASSED | PASS |
| CKV_AWS_17 | sec_rds_public_access_bad.tf | sec_rds_public_access_good.tf | FAILED | FAILED | PASSED | PASSED | PASS |
| Cost gate (pass) | infracost_payments_db_pass.json | — | exit 0 | exit 0 ($39.71) | — | — | PASS |
| Cost gate (fail-high) | infracost_payments_db_fail_high.json | — | exit 1 | exit 1 ($147.04) | — | — | PASS |
| Cost gate (fail-low) | infracost_payments_db_fail_low.json | — | exit 1 | exit 1 ($20.00) | — | — | PASS |

---

## 2. Demo Scenario Discrimination Check — terraform/staging/main.tf

**Command:**
```
checkov -f terraform/staging/main.tf --check CKV_AWS_24,CKV_AWS_16,CKV_AWS_17 --compact
```

**Expected discrimination pattern:**
- `aws_security_group.app_tier` → CKV_AWS_24 FAILED (SSH port 22 open to 0.0.0.0/0)
- `aws_db_instance.payments_db` → CKV_AWS_16 PASSED (storage_encrypted = true)
- `aws_db_instance.payments_db` → CKV_AWS_17 PASSED (publicly_accessible = false)

**Actual result:**
- `aws_security_group.app_tier` → CKV_AWS_24 **FAILED** (correct)
- `aws_db_instance.payments_db` → CKV_AWS_16 **PASSED** (correct)
- `aws_db_instance.payments_db` → CKV_AWS_17 **PASSED** (correct)

**Verdict: The demo discrimination pattern holds.** The security gate flags the SG misconfiguration (SSH port 22 open to the internet) and passes the correctly-configured RDS instance. The demo narrative is intact.

---

## 3. Failures

None. All fixtures and the demo scenario check produced the expected results.

---

## 4. Cost Gate Constants Verification

Verified from `gates/cost_gate.py` and reconciled against `research/findings/finops-rds-postgres-cost-reference.md`:

| Constant | Spec value | Implementation value | Match |
|---|---|---|---|
| TARGET_RESOURCE | aws_db_instance.payments_db | aws_db_instance.payments_db | PASS |
| REFERENCE_COST | 39.71 | 39.71 | PASS |
| TOLERANCE | 4.00 | 4.0 | PASS |
| RANGE_LOW | 35.71 | 35.71 | PASS |
| RANGE_HIGH | 43.71 | 43.71 | PASS |

---

## 5. Fixture Change Log (this run)

**Updated fixtures (port 8080 → port 22, targeting CKV_AWS_24 not CKV_AWS_277):**

- `tests/fixtures/sec_sg_open_ingress_bad.tf` — description updated to "SSH open to internet (bad)"; `from_port`/`to_port` changed from 8080 to 22.
- `tests/fixtures/sec_sg_open_ingress_good.tf` — description updated to "SSH restricted to VPC"; `from_port`/`to_port` changed from 8080 to 22.

These changes align the fixtures with the corrected researcher spec (`research/findings/sec-sg-open-ingress.md`) and the updated demo Terraform (`terraform/staging/main.tf`). CKV_AWS_277 (all-traffic / protocol=-1) is no longer referenced as the primary demo check; CKV_AWS_24 (SSH / port 22) is the authoritative check, as confirmed by this run.

---

## 6. Coverage Verdict

**Gate-accuracy spine: CLOSED**

| Gate | Coverage | Status |
|---|---|---|
| CKV_AWS_24 (SG SSH ingress) | Known-bad flags, known-good passes, demo TF discriminates correctly | PASS |
| CKV_AWS_16 (RDS encryption at rest) | Known-bad flags, known-good passes | PASS |
| CKV_AWS_17 (RDS public access) | Known-bad flags, known-good passes | PASS |
| Cost gate — pass fixture | exit 0, $39.71 | PASS |
| Cost gate — fail-high fixture | exit 1, $147.04 | PASS |
| Cost gate — fail-low fixture | exit 1, $20.00 | PASS |
| Demo main.tf discrimination | SG fails CKV_AWS_24; RDS passes CKV_AWS_16 and CKV_AWS_17 | PASS |

**All six acceptance criteria are met:**
- [x] CKV_AWS_24: known-bad (port 22, 0.0.0.0/0) flagged — PASSED
- [x] CKV_AWS_24: known-good (port 22, 10.0.0.0/16) passes — PASSED
- [x] CKV_AWS_16: known-bad flagged, known-good passes — PASSED
- [x] CKV_AWS_17: known-bad flagged, known-good passes — PASSED
- [x] terraform/staging/main.tf: SG fails CKV_AWS_24, RDS passes CKV_AWS_16 + CKV_AWS_17 — PASSED
- [x] Cost gate: pass fixture → exit 0 ($39.71), fail-high → exit 1 ($147.04), fail-low → exit 1 ($20.00) — PASSED
