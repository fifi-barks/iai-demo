# IAI Demo Scenario — LOCKED v1

*Decisions locked 2026-06-04. Paste into `iai-demo/README.md`'s scenario slots. This is the single narrative the LinkedIn video tells.*

**Locked:** AWS ap-southeast-5 (Kuala Lumpur) + GCP asia-southeast1 (Singapore) · payments service · one authentic security catch · annotated YAML manifest.

## The one-line story
A platform engineer asks, in plain English, for a staging environment for the payments service spanning **AWS + GCP**. IAI reads the manifest, generates the Terraform, runs the three gates, hands back **one human-readable card**, the human taps approve, it applies, and the manifest updates itself.

## Intent prompt (typed into Telegram)
> "Stand up a staging environment for the **payments** service: a managed Postgres, an app compute tier, and a private network in **AWS**, plus an object-storage bucket in **GCP** for export files. Tag it staging, owner payments-team."

One sentence. No tool names, no resource syntax. That contrast — sentence in, governed infrastructure out — is the whole pitch.

## Clouds in scope
**AWS ap-southeast-5** (Kuala Lumpur, Malaysia) — network, Postgres, app tier. **GCP asia-southeast1** (Singapore) — export bucket. Two clouds both doing real work, so "multi-cloud under one intent layer" is shown, not claimed. The pair is deliberate: GCP uses **labels** where AWS uses **tags**, so the agent reconciling the two metadata models is a live, on-camera demonstration of the normalization layer. The regional proximity (KL ↔ Singapore) reflects a realistic Southeast Asia deployment topology. **Physical-Cisco leg omitted for v1** — declared in the manifest as out-of-scope so the architecture reads complete, but not built (switches can't be filmed).

## Resources provisioned (~7–8, deliberately small)
- AWS VPC + private subnet
- AWS managed Postgres (RDS) — **data-bearing**
- AWS app compute tier (depends on the Postgres; reached via a security group)
- GCP object-storage bucket (export files)
- Supporting IAM / security-group glue

## What each gate must catch (the credibility core)
The gates must be visibly, *accurately* doing real work — not a green rubber stamp.

- **Security gate — one authentic catch.** The generated app-tier security group would allow **SSH (port 22) open to `0.0.0.0/0`** — a textbook remote-admin exposure and one of the most common real-world misconfigurations, exactly what Checkov/tfsec exist to flag (CKV_AWS_24). The gate catches it accurately and the summary states it plainly ("the app tier would have been reachable via SSH from the entire internet — I've restricted ingress to the VPC"). This is framed as *the kind of default humans miss*, not a planted bug. Show clean checks alongside it (Postgres not publicly accessible — passes; encryption-at-rest on — passes) so the catch reads as discrimination, not noise.
- **Cost gate.** Infracost returns a monthly estimate with the **Postgres as the dominant line item**; the summary gives a single number and names the driver ("~\$X/mo, mostly the db.* instance"). Reference figure is for **ap-southeast-5** — see `research/findings/finops-rds-postgres-cost-reference.md` for the current locked number.
- **Plan gate.** "7 resources to add, 0 to change, 0 to destroy," with the critical ones flagged.

## Criticality + transitivity (shown, not narrated)
The Postgres is tagged **critical** (data-bearing). The app tier references it, so it **inherits critical** through the dependency graph — the summary shows both as critical though the human only tagged the database. Because critical + data-bearing resources are in play, the agent states it will **snapshot before applying** (infra state + native DB snapshot). One beat demonstrates criticality transitivity *and* data-aware rollback.

## The magic moment (the screenshot people share)
Seconds after the one-sentence Telegram message, the human gets back a single card:

> **Staging environment for payments — ready to build**
> • 7 resources across AWS + GCP
> • Cost: ~\$X/month (mostly the Postgres instance)
> • Security: 1 issue caught and fixed — the app tier would have been reachable via SSH (port 22) from the entire internet (`0.0.0.0/0`); ingress restricted to the VPC. All other checks pass.
> • Critical: payments-db (data) and app-tier (depends on it). I'll snapshot before applying.
> **[ Approve ]  [ Decline ]**

Tap **Approve** → it applies → the manifest rewrites itself with the new state. End on the diff of the self-updated manifest.

## Manifest format
**Annotated YAML** for v1 — round-trips cleanly, which the auto-update requirement demands. *Build note for the Developer:* use a comment-preserving YAML library (e.g. `ruamel.yaml`) so the ADR-style annotations survive the agent's rewrite after apply. MDX is the richer ADR-storytelling format — flagged as the v2 evolution, not now.

## Why this scenario
Small enough to build and film, but it exercises every differentiator in one pass: multi-cloud with a visible normalization contrast, manifest-driven generation, all three gates with an accurate security catch, criticality transitivity, data-aware rollback, the synthesized approval UX, and the self-updating manifest. Nothing is filler.
