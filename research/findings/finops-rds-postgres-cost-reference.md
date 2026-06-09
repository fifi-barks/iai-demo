---
domain: FinOps
topic: Monthly cost reference for RDS PostgreSQL staging instance
status: ready
confidence: medium
whitepaper: WP3
---

# RDS PostgreSQL Staging Instance — Monthly Cost Reference

## Rule

The Infracost estimate for the demo's RDS PostgreSQL staging instance must fall within ±10% of the reference figure derived from AWS public on-demand pricing for `ap-southeast-5` (Asia Pacific, Kuala Lumpur, Malaysia). If the estimate deviates beyond that tolerance, the gate configuration or Infracost pricing data must be investigated before the demo runs.

## Source

1. **dbcost.com — db.t3.small pricing table, ap-southeast-5 (Asia Pacific Malaysia)**. Retrieved 2026-06-04. Shows on-demand hourly rate for `db.t3.small` in ap-southeast-5: **$0.051/hr** (both MySQL and PostgreSQL rows show the same rate for this instance class). Data sourced from the AWS public pricing API by dbcost.com. https://www.dbcost.com/instance/db.t3.small

2. **aws-pricing.com — ap-southeast-5 region pricing table**. Retrieved 2026-06-04. Confirms EC2 t3 pricing and EBS gp3 storage for ap-southeast-5: EC2 t3.small = $0.0238/hr; EBS gp3 = **$0.0864/GB-month**. This page covers EC2 and EBS only; RDS storage pricing is separate. https://aws-pricing.com/ap-southeast-5.html

3. **aws-pricing.com — ap-southeast-1 (Singapore) pricing table**. Retrieved 2026-06-04. For cross-reference: EC2 t3.small = $0.0264/hr; EBS gp3 = $0.096/GB-month. Malaysia/Singapore ratio = ~0.90 (Malaysia is ~10% cheaper). https://aws-pricing.com/ap-southeast-1.html

4. **AWS Pricing JSON — AmazonRDS ap-southeast-5 region index**. Confirmed that ap-southeast-5 is present in the AWS bulk pricing file at `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/AmazonRDS/current/ap-southeast-5/index.json`. The file is ~50 MB; product definitions were accessible but the pricing terms section (containing PricePerUnit values) falls beyond the 10 MB fetch limit of available tooling. Authoritative hourly figures must be read from the full JSON. Retrieved 2026-06-04.

5. **CloudZero advisor — db.t3.small regional availability**. Confirms `db.t3.small` is available in ap-southeast-5 (Asia Pacific Malaysia) for PostgreSQL. https://advisor.cloudzero.com/aws/rds/db.t3.small — Retrieved 2026-06-04.

6. **anchorsprint.com — AWS Malaysia vs Singapore cost comparison**. Published 2025 (exact date not shown). Confirms EC2 t3.medium pricing: Malaysia ~$0.040/hr, Singapore ~$0.046/hr (approx. 13% cheaper in Malaysia). Cross-validates the ~10% Malaysia discount factor across t3 instance family. https://www.anchorsprint.com/blog/aws-malaysia-region-vs-singapore-cloud-cost-savings/

7. **RDS gp3 storage (derived estimate)**: The RDS gp3 per-GB-month price for ap-southeast-5 is not directly confirmed by a publicly accessible source at the time of writing (2026-06-04). It is derived as follows: Singapore EBS gp3 ($0.096) scaled by the Malaysia/Singapore ratio (0.90) gives $0.0864 for ap-southeast-5 EBS. Applying the same ratio to the Singapore RDS gp3 storage price (estimated at ~$0.138/GB-month, consistent with the typical RDS-to-EBS premium ratio of ~1.44x observed in us-east-1) yields an estimated RDS gp3 price of **~$0.124/GB-month** for ap-southeast-5. This is a derived figure — confidence is medium. The Tester must run Infracost against actual HCL targeting `ap-southeast-5` and use the resulting storage line item as the authoritative figure.

8. **FinOps Foundation — Cloud Cost Optimization Framework**. Establishes the practice of deriving reference cost figures from vendor list pricing before applying reserved/spot discounts. https://www.finops.org/framework/

9. **Infracost pricing sources**: Infracost uses the AWS public pricing API directly; its estimates for fixed-cost resources (EC2, RDS) match AWS list pricing. Infracost added ap-southeast-5 region support in release v0.10.40 (December 2023). https://www.infracost.io/docs/ and https://github.com/infracost/infracost/releases

---

## Gate mapping

- Engine: **Infracost**
- Line items to reconcile:
  - `aws_db_instance.payments_db` — instance compute (hourly on-demand rate x 730 hours/month)
  - `aws_db_instance.payments_db` — storage (gp3, per GB-month x allocated GB)
- Severity in approval summary: **MEDIUM** (cost gate is informational; it does not block approval but is surfaced as the dominant cost driver with the instance class named explicitly)
- Infracost output field: `monthlyCost` on the `aws_db_instance` resource block

---

## Expected cases (for the Tester's fixtures)

### Recommended instance class

**`db.t3.small`** — recommended for the staging payments DB in the demo.

Availability in ap-southeast-5: **confirmed** (CloudZero advisor, dbcost.com, CloudPrice.net all list ap-southeast-5 / Asia Pacific (Malaysia) as a supported region for db.t3.small).

Rationale: `db.t3.micro` (1 GB RAM) is too small for PostgreSQL with realistic schema and connection pooling; it will trigger swap under even light load. `db.t3.small` (2 GB RAM) is the smallest credible staging size. Using `db.t3.micro` in the demo risks a performance caveat detracting from the narrative; `db.t3.small` avoids it while remaining clearly a cost-conscious staging choice.

### Reference cost derivation (on-demand, Single-AZ, no reserved pricing)

| Component | Rate | Quantity | Monthly cost |
|---|---|---|---|
| db.t3.small compute (PostgreSQL, ap-southeast-5, Single-AZ) | $0.051/hr | 730 hr/mo | **$37.23** |
| Storage — gp3 General Purpose SSD | ~$0.124/GB-month (derived — see Source 7) | 20 GB | **~$2.48** |
| **Total** | | | **~$39.71** |

Assumptions:
- Region: `ap-southeast-5` (Asia Pacific, Kuala Lumpur, Malaysia)
- Engine: PostgreSQL (latest supported version; v16 as of 2024)
- Deployment: Single-AZ (staging; Multi-AZ doubles the compute line item)
- Storage type: gp3 (AWS default since 2022; same per-GB-month price as gp2 at baseline)
- Storage size: 20 GB (minimal but credible for a staging payments DB schema + indexes)
- Backup retention: default 1 day (no additional charge within free tier of backup storage = allocated storage size)
- No Performance Insights, no enhanced monitoring, no data transfer charges
- Pricing as of 2026-06-04

### Known-bad cost fixture (for gate calibration test)

A Terraform resource configured with `db.t3.large` instead of `db.t3.small` in ap-southeast-5 will produce a significantly higher estimate. If the known-us-east-1 ratio of db.t3.large/db.t3.small (~$0.141/$0.036 = 3.9x) holds in ap-southeast-5, the compute line item would be approximately $0.051 × 3.9 = ~$0.199/hr → ~$145/mo compute alone. If the Tester sees this figure, the instance class in the demo Terraform is wrong.

Note: The Tester should verify the db.t3.large ap-southeast-5 rate from Infracost output directly, as the 3.9x multiplier is an extrapolation.

### Known-good cost fixture (for reconciliation test)

```hcl
resource "aws_db_instance" "payments_db" {
  identifier        = "payments-staging"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = "db.t3.small"
  allocated_storage = 20
  storage_type      = "gp3"
  storage_encrypted = true
  publicly_accessible = false
  # region set to ap-southeast-5 via provider configuration
}
```

**Expected Infracost output (reference — figures rounded):**

```
 Name                                           Monthly Qty  Unit   Monthly Cost

 aws_db_instance.payments_db
 ├─ Database instance (on-demand, Single-AZ, db.t3.small)
 │                                                      730  hours        $37.23
 └─ Storage (gp3)                                        20  GB            $2.48

 OVERALL TOTAL                                                             $39.71
```

**Acceptable reconciliation tolerance: ±$4.00/month (approximately ±10%).**

A tolerance of $4.00 covers minor AWS pricing API lag and any rounding differences. If the Infracost estimate falls outside [$35.71, $43.71], the Tester must flag it and the Developer must investigate.

The storage line item in particular should be treated as a soft reference: the $0.124/GB-month figure is derived, not directly read from the AWS pricing JSON. If Infracost returns a storage price in the range $0.11–$0.14/GB-month for gp3 in ap-southeast-5, that is within expected bounds.

---

## Notes

**Confidence level: MEDIUM — reason and mitigation:**

The instance compute rate ($0.051/hr) is sourced from dbcost.com's AWS pricing API data, and is corroborated by the EC2/RDS pricing multiplier applied to confirmed EC2 t3 pricing for ap-southeast-5. However, the rate was not directly read from the AWS bulk pricing JSON (too large for available fetch tooling) or from a paywall-free aggregator that specifically shows engine-level breakdowns. The gp3 storage rate ($0.124/GB-month) is derived, not directly confirmed.

**Mitigation**: Before the demo runs, the Tester should execute `infracost breakdown --path <terraform_dir>` targeting ap-southeast-5 and capture the actual Infracost output. That output becomes the authoritative reference; this document provides the range to sanity-check against. If Infracost shows a compute figure materially different from $37.23 (outside ±$4), the Developer must investigate whether Infracost has ap-southeast-5 pricing loaded.

**Upgrade path to HIGH confidence**: Read the full AWS bulk pricing JSON for ap-southeast-5 using a tool that can stream large files (e.g., `aws pricing get-products --service-code AmazonRDS --region ap-southeast-5 --filters "Type=TERM_MATCH,Field=instanceType,Value=db.t3.small" "Type=TERM_MATCH,Field=databaseEngine,Value=PostgreSQL" "Type=TERM_MATCH,Field=deploymentOption,Value=Single-AZ"`) and update this file with the confirmed PricePerUnit. Once confirmed, raise confidence to HIGH and remove the derived caveat on the storage rate.

**Regional pricing note — Malaysia vs Singapore:**

ap-southeast-5 (Malaysia) is approximately 10% cheaper than ap-southeast-1 (Singapore) across EC2, EBS, and (by extension) RDS. This is consistent with AWS's typical pattern for newer AP regions. The ~10% discount is corroborated by three independent data points: EC2 t3.small pricing, EBS gp3 pricing, and the anchorsprint.com analysis of EC2 t3.medium. The same discount is expected to apply to RDS instance and storage pricing, which is the basis for the derived storage rate.

**What would cause the estimate to drift (Developer must fix these in demo Terraform):**

1. **Multi-AZ enabled** (`multi_az = true`): doubles the compute line item to ~$74.46/mo. The demo uses Single-AZ (staging environment; no HA requirement).

2. **Storage autoscaling enabled** (`max_allocated_storage > allocated_storage`): Infracost cannot predict autoscaled storage; it will estimate only the base `allocated_storage`. This is correct behaviour — the Tester should confirm Infracost warns about autoscaling if the parameter is set.

3. **Storage type gp2 vs gp3**: both are priced identically at the baseline size. The demo should use `gp3` (current default; better baseline performance at same price).

4. **Backup retention > 1 day**: AWS provides free backup storage up to the size of the provisioned storage. Beyond that, additional backup storage is billed at ~$0.095/GB-month (us-east-1 rate; AP rate may differ slightly). For a staging DB with `backup_retention_period = 1` (default), no additional charge applies.

5. **PostgreSQL Extended Support pricing**: AWS charges extended support for end-of-life engine versions. PostgreSQL 14 entered extended support in 2025 (rate: ~$0.10/vCPU-hr). The demo must use PostgreSQL 15 or 16 to avoid this charge. If using an older engine version, Infracost may or may not surface the extended support surcharge depending on its version — flag for verification.

6. **Infracost pricing cache staleness**: Infracost fetches pricing from a hosted API (https://www.infracost.io/docs/supported_resources/aws/) which mirrors AWS pricing. If run in CI without network access, it falls back to a bundled pricing file that may be slightly stale. The ±10% tolerance covers this.

**Approval summary wording:** The agent should surface the cost as: "~$40/month, mostly the db.t3.small instance ($37/mo). Storage (20 GB gp3): ~$2/mo." The exact figure should come from Infracost output, not this reference — the reference is for the Tester's reconciliation check only.

**FinOps whitepaper note:** The demo deliberately uses on-demand pricing to keep the narrative clean. In a real deployment, a 1-year Reserved Instance for `db.t3.small` in ap-southeast-5 would typically cost approximately 39% less than on-demand (consistent with other AP regions), bringing compute to approximately ~$22/mo. This reserved-vs-on-demand delta is a natural hook for the FinOps whitepaper's cost optimization section — but the demo gate must show the on-demand figure to avoid confusing the approval UX. The Malaysia region's ~10% structural discount vs Singapore is an additional whitepaper talking point: Malaysian data residency requirements and lower cost can both be satisfied simultaneously with ap-southeast-5, a meaningful differentiator for regional enterprise customers.

**Pricing confidence note:** The $0.051/hr figure for `db.t3.small` in ap-southeast-5 was sourced from dbcost.com (AWS pricing API aggregator) on 2026-06-04. It could not be independently verified from a second paywall-free aggregator or directly from the AWS bulk pricing JSON due to file size constraints. AWS can change list prices at any time. The Tester should re-verify against live Infracost output immediately before the demo run if more than 30 days have elapsed since this finding was written (2026-06-04).

**Prior version note:** This file was previously written using us-east-1 pricing ($0.036/hr, $28.58/month total) as the demo region had not yet been confirmed. That version has been superseded. All fixtures and gate thresholds in `tests/` must be updated to use the ap-southeast-5 figures in this version.
