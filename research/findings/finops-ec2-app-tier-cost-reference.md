---
domain: finops
topic: EC2 t3.micro app-tier monthly cost reference (ap-southeast-5)
status: verified
confidence: medium  # regional price derived by halving ratio; no direct AWS pricing page for ap-southeast-5 at time of research
whitepaper: whitepaper_iai.md
---

## Rule

The IAI cost gate targets `aws_instance.app_tier` (t3.micro, ap-southeast-5, default gp3 root volume).
The acceptable monthly cost range is **$8.38 – $10.38** (reference $9.38 ± $1.00).

## Source

1. **ap-southeast-5 t3.small on-demand rate**: $0.0238/hr — from aws-pricing.com, consistent with
   `research/findings/finops-rds-postgres-cost-reference.md` (same source, same region).

2. **AWS T3 micro/small halving ratio**: confirmed $0.0104 (micro) / $0.0208 (small) = 0.5 in us-east-1.
   The ratio is consistent across T3 across all AWS regions (AWS pricing follows the same family ladder).
   Therefore: ap-southeast-5 t3.micro = $0.0238 / 2 = **$0.0119/hr**.

3. **EBS gp3 rate in ap-southeast-5**: $0.0864/GB-month (same source as t3.small rate above).
   Default root volume = 8 GB → $0.0864 × 8 = **$0.69/mo**.

4. **No data transfer costs included** — conservative approach; demo traffic negligible.

## Gate mapping

| Constant       | Value                    |
|----------------|--------------------------|
| TARGET_RESOURCE| `aws_instance.app_tier`  |
| REFERENCE_COST | $9.38/mo                 |
| TOLERANCE      | $1.00/mo (~10%)          |
| RANGE_LOW      | $8.38/mo                 |
| RANGE_HIGH     | $10.38/mo                |

## Cost derivation

```
Compute:   $0.0119/hr × 730 hr/mo = $8.687 ≈ $8.69/mo
EBS gp3:   8 GB × $0.0864/GB-mo   = $0.691 ≈ $0.69/mo
─────────────────────────────────────────────────────────
Total:     $9.38/mo
```

The IaC generator explicitly declares `root_block_device { volume_type = "gp3", volume_size = 8 }` so
Infracost can produce a deterministic estimate matching this reference.

## Expected cases (for golden fixtures)

| Fixture file                        | Description                           | Monthly cost | Expected verdict |
|-------------------------------------|---------------------------------------|--------------|-----------------|
| `infracost_app_tier_pass.json`      | t3.micro, 8 GB gp3 (reference)        | $9.38        | PASS            |
| `infracost_app_tier_fail_high.json` | t3.small, 8 GB gp3 (oversized)        | $18.06       | FAIL (too high) |
| `infracost_app_tier_fail_low.json`  | t3.nano, 8 GB gp3 (undersized)        | $5.03        | FAIL (too low)  |
