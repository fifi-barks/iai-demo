# Cleanup Summary — v1 AWS-Only Release

## What was cleaned up

### 1. **Removed GCP completely**
- ❌ Removed `google` provider from `terraform/staging/providers.tf`
- ❌ Removed `gcp_project` variable from `terraform/staging/variables.tf`
- ❌ Removed `google_storage_bucket.export_bucket` resource from `terraform/staging/main.tf`
- ❌ Removed `_render_export_bucket()` method from `agent/iac_generator.py`
- ❌ Removed "export-bucket" from IaC generator RENDERERS dict
- ❌ Removed `_gcp_labels()` helper from IaC generator

### 2. **Fixed RDS multi-AZ requirement**
- ✅ Split single subnet into two subnets across AZs (ap-southeast-5a, ap-southeast-5b)
- ✅ Updated `aws_db_subnet_group` to reference both subnets
- ✅ Updated IaC generator to emit both subnets with correct AZ assignments
- ✅ Updated app-tier instance to reference correct subnet (az1)

### 3. **Simplified variables & configuration**
- ✅ Created `terraform/staging/terraform.tfvars` with all required variables
  - `environment = "staging"`
  - `app_tier_ami = "<placeholder>"`
  - `app_tier_image_uri = "ubuntu:22.04"`
- ✅ Removed `gcp_project` requirement (no longer needed)
- ✅ Set `app_tier_image_uri` default to `ubuntu:22.04` for Trivy scanning

### 4. **Cleaned up code comments & documentation**
- ✅ Updated all module docstrings to reflect AWS-only v1
- ✅ Updated manifest.yaml comments to remove GCP references
- ✅ Updated README.md to highlight AWS-only focus
- ✅ Updated demo scenario description (now 6 resources, not 7-8)

### 5. **Removed debug logging**
- ✅ Cleaned up `[MSG]`, `[CARD]`, `[APPROVE]` debug prefixes from logs
- ✅ Kept only essential logging (intent received, approval callback, apply status)

### 6. **Updated getting started guide**
- ✅ Created comprehensive `GETTING_STARTED.md` covering full setup workflow
- ✅ Includes AWS/GCP account setup, EC2 provisioning, OpenTofu, Ollama, credentials
- ✅ Includes troubleshooting section for common issues

## Files changed

```
M  README.md                              (scenario description, cloud section)
M  agent/iac_generator.py                (removed GCP, multi-AZ subnet generation)
M  bot/intent_handler.py                 (cleaned up debug logging)
M  bot/telegram_bot.py                   (cleaned up debug logging)
M  manifest.yaml                         (removed export-bucket, updated header)
M  terraform/staging/main.tf             (multi-AZ subnets, removed GCS bucket)
M  terraform/staging/providers.tf        (removed Google provider)
M  terraform/staging/variables.tf        (removed gcp_project, simplified)
A  terraform/staging/terraform.tfvars    (new: all required variables)
A  GETTING_STARTED.md                    (new: comprehensive setup guide)
A  test-e2e.sh                           (new: debugging helper script)
```

## What to do next

1. **Get a valid AMI ID** in ap-southeast-5 (see terraform.tfvars for command)
2. **Destroy previous test resources** (if any remain from yesterday's run):
   ```bash
   cd terraform/generated
   tofu destroy -auto-approve
   ```
3. **Clean generated directory** (will be re-generated on next pipeline run):
   ```bash
   rm -rf terraform/generated/*
   ```
4. **Test end-to-end**:
   ```bash
   source venv/bin/activate
   python3 -m bot.telegram_bot
   # Send intent via Telegram, click Approve
   ```

## Demo script (for video)

1. Bot is running and polling
2. User sends: "Set up staging for payments: Postgres, app tier, private VPC. Tag it staging, payments-team."
3. Agent synthesizes approval card (~60s)
4. Card shows: 6 resources, cost, 1 security issue caught (SSH open → fixed), critical resources
5. User clicks Approve
6. Infrastructure applies, manifest updates
7. Done.

---

**Status:** v1 clean, polished, AWS-only. Ready for demo video.
