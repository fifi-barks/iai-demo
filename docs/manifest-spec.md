# Platform Manifest — Spec

The manifest is the heart of IAI. It declares **which IaC engine owns each environment/resource type**, carries criticality, and is **agent-maintained** after every apply. The agent reads it to decide tooling — no guessing.

## Format decision

**Decision: annotated YAML** (date: 2026-06-04)

Inline YAML comments carry the ADR-style rationale. Annotated YAML round-trips cleanly, which the auto-update requirement demands. The agent uses **`ruamel.yaml`** (Python) to preserve all human-authored comments on every rewrite — standard `PyYAML` strips comments and must not be used.

MDX is the richer ADR-storytelling format; flagged as a v2 evolution, not in scope for the demo.

---

## Required properties

| Property | Description |
|---|---|
| `manifest_version` | Schema version string. Increment on breaking changes. |
| `environments.<name>.engine` | IaC engine that owns this environment: `opentofu` or `ansible`. |
| `environments.<name>.clouds` | List of cloud providers in scope for this environment. |
| `environments.<name>.regions` | Map of cloud provider → default region for this environment (e.g. `aws: ap-southeast-5`). Resources inherit unless overridden. |
| `environments.<name>.tags` | Key/value metadata applied to all resources (agent normalises AWS tags ↔ GCP labels). |
| `resources.<name>.cloud` | Which cloud provider hosts this resource. |
| `resources.<name>.type` | OpenTofu resource type (e.g. `aws_db_instance`, `google_storage_bucket`). |
| `resources.<name>.criticality` | Required on every resource. One of: `critical`, `high`, `medium`, `low`. No tag → no provision (greenfield rule). |
| `resources.<name>.depends_on` | List of sibling resource names this resource references. Drives criticality transitivity. |
| `resources.<name>.data_bearing` | `true` on any resource holding persistent data. Triggers native provider snapshot before apply. |
| `resources.<name>.state` | **Agent-maintained block.** Written/updated after every apply. Never edit manually. |

### Criticality transitivity rule

If resource B appears in resource A's `depends_on` list, B's effective criticality is `max(B.criticality, A.criticality)`. The agent resolves transitivity across the full dependency graph before generating IaC and before presenting the approval summary — a human never needs to tag transitive dependents.

### Auto-update contract

After a successful apply the agent rewrites only the `state:` block of each affected resource. All `# Why:` comments, `criticality`, `engine`, `clouds`, `tags`, and `depends_on` values are **read-only from the agent's perspective** — the human owns them. `ruamel.yaml` guarantees comment preservation; any auto-update that silently destroys a comment is a bug.

---

## Schema — full annotated example (payments staging, v1)

```yaml
# Platform Manifest — payments service, v1
# Why: staging environment for the payments service spanning AWS (network + data + compute)
# and GCP (export storage). Mirrors prod topology at reduced scale; provisioned greenfield.
#
# Auto-update note: the agent rewrites only `state:` blocks after apply.
# All other fields and comments are human-owned. Library: ruamel.yaml.

manifest_version: "1"

environments:

  staging:
    # Why: isolated staging environment for the payments service.
    engine: opentofu
    clouds: [aws, gcp]
    regions:
      aws: ap-southeast-5      # Kuala Lumpur, Malaysia — default for all AWS resources
      gcp: asia-southeast1     # Singapore — default for all GCP resources
    # Note: GCP uses 'labels' where AWS uses 'tags'. The agent normalises both from the
    # intent prompt before generating IaC — the on-camera contrast demonstrates the
    # normalization layer without extra narration.
    tags:
      environment: staging
      owner: payments-team

    resources:

      payments-vpc:
        # Why: private network boundary for all AWS resources in this environment.
        # Network isolation is a prerequisite for the data-snapshot rollback guarantee.
        cloud: aws
        type: aws_vpc
        criticality: high
        depends_on: []
        # Agent-maintained — do not edit:
        state:
          status: pending        # pending | applied | failed
          resource_id: ~         # e.g. vpc-0abc1234 after apply
          last_applied: ~

      payments-db:
        # Why: managed Postgres holding payments transaction records.
        # Data-bearing → triggers infra-state snapshot + native RDS snapshot before apply.
        # Criticality is transitive: any resource in depends_on that references this one
        # inherits 'critical' even if tagged lower.
        cloud: aws
        type: aws_db_instance    # RDS Postgres
        criticality: critical
        data_bearing: true
        depends_on: [payments-vpc]
        # Agent-maintained — do not edit:
        state:
          status: pending
          resource_id: ~         # e.g. payments-db-staging after apply
          endpoint: ~
          last_applied: ~

      app-tier:
        # Why: compute tier serving the payments API.
        # Depends on payments-db via security group; inherits critical through transitivity.
        # Security gate will flag 0.0.0.0/0 inbound if the generator emits it — gate must
        # catch this and restrict ingress to the VPC CIDR before the summary is shown.
        cloud: aws
        type: aws_instance
        criticality: critical    # inherited from payments-db via transitivity
        depends_on: [payments-db, payments-vpc]
        # Agent-maintained — do not edit:
        state:
          status: pending
          resource_id: ~
          last_applied: ~

      export-bucket:
        # Why: GCP object-storage bucket for payments export files.
        # Deliberately cross-cloud to demonstrate multi-cloud normalisation on camera.
        # Must NOT default to public-read — security gate flags this as a critical finding.
        cloud: gcp
        type: google_storage_bucket
        criticality: high
        depends_on: []
        # Agent-maintained — do not edit:
        state:
          status: pending
          resource_id: ~         # bucket name after apply
          last_applied: ~

  edge-network:
    # Why: physical Cisco switching layer. Declared for architectural completeness;
    # not built in demo v1 — switches can't be filmed.
    # Revisit for v2 if a physical networking leg is added.
    engine: ansible
    scope: out-of-scope-v1
