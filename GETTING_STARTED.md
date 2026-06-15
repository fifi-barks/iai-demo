# IAI Demo — Getting Started Guide

**Infrastructure as Intent (IAI)**: An AI agent that transforms plain-language business intent into validated, cost-optimized infrastructure across multiple clouds in one approval workflow.

This guide covers the complete setup to run the IAI proof-of-concept (POC) locally or on a cloud VM.

---

## Prerequisites

- **OS:** Linux (Ubuntu 22.04 LTS recommended) or macOS
- **Hardware:** t3.medium EC2 instance (4 GB RAM minimum; t3.small causes Ollama memory exhaustion)
- **AWS account** with permissions to create EC2, VPC, RDS, IAM roles
- **GCP account** with compute and storage APIs enabled
- **Telegram bot token** (create via BotFather on Telegram)
- **Git** installed
- **Python 3.10+**

---

## 1. AWS & GCP Account Setup

### 1.1 AWS Account

1. **Create AWS account** or use existing
2. **Create IAM user or use root** (for demo only; production: use least-privilege)
3. **Note region:** Demo uses `ap-southeast-5` (Kuala Lumpur, Malaysia) — **not us-east-1**
4. **Create budget alert:**
   - Go to AWS Billing Console → Budgets → Create Budget
   - Set monthly limit ~$50 (staging resources typically cost $5–15/month)

### 1.2 GCP Account

1. **Create GCP project** or use existing
2. **Enable APIs:**
   - Compute Engine API
   - Cloud Storage API
   - Identity and Access Management API
3. **Note region:** Demo uses `asia-southeast1` (Singapore)
4. **Create budget alert** in GCP console (Billing → Budgets)

---

## 2. EC2 Instance Setup (Keyless Credentials)

IAI runs on an EC2 instance with **no static credentials** in code or environment. Credentials are sourced from:
- **AWS:** EC2 instance role (IMDSv2)
- **GCP:** Workload Identity Federation (WIF) — AWS EC2 role federated to GCP service account

### 2.1 Launch EC2 Instance

```bash
# In AWS console:
# 1. EC2 Dashboard → Instances → Launch Instance
# 2. Select: Ubuntu 22.04 LTS (free tier eligible)
# 3. Instance Type: t3.medium (NOT t3.small — Phi 3.8B needs 4GB RAM)
# 4. Network: default VPC
# 5. IAM Role: (we'll create this next)
# 6. Storage: 30 GB (default)
# 7. Security Group: Allow SSH (22) from your IP, HTTP (80), HTTPS (443)
# 8. Launch
```

### 2.2 Create IAM Instance Role

```bash
# In AWS console → IAM:
# 1. Roles → Create Role
# 2. Trusted Entity: AWS Service → EC2
# 3. Permissions: Attach `AdministratorAccess` (demo only; prod = least-privilege)
# 4. Name: `iai-demo-role`
# 5. Create
#
# Back to EC2 instance:
# 6. Select instance → Instance Details → IAM Role → Modify → `iai-demo-role`
```

### 2.3 Set Up Workload Identity Federation (WIF) for GCP

```bash
# In GCP console:
# 1. IAM & Admin → Service Accounts → Create Service Account
#    Name: iai-demo-sa
#    Grant roles: Editor (demo only; prod = principle of least privilege)
#
# 2. IAM & Admin → Workload Identity Pools → Create Pool
#    Pool ID: aws-iai-pool
#    Provider Type: AWS
#    AWS Account ID: (your AWS account ID)
#    Provider ID: aws-iai-provider
#
# 3. Add Provider attribute mapping:
#    AWS ARN → google.subject
#    AWS Account ID → google.subject (for role assumption)
#
# 4. Service Accounts → (select iai-demo-sa) → Grant Access
#    New Principal: principalSet://goog/subject/iam.amazonaws.com/role/iai-demo-role
#    Role: Editor
#
# 5. Save GCP Project ID and WIF Pool Resource Name (you'll need these)
```

### 2.4 SSH into EC2

```bash
ssh -i /path/to/key.pem ubuntu@your-ec2-public-ip
```

---

## 3. Clone Repository & Install Dependencies

```bash
# On the EC2 instance:
cd ~
git clone <your-iai-demo-repo-url>
cd iai-demo

# Create Python venv
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Verify installations
pip list | grep -E "boto3|checkov|requests|Flask"
```

### 3.1 Verify Requirements

Current `requirements.txt` should include:
```
ruamel.yaml>=0.18
python-telegram-bot>=20.0
boto3>=1.34
checkov>=3.0
requests>=2.31
Flask>=2.0
```

---

## 4. Ollama + Phi 3.8B Model Setup

The IAI agent uses **Phi 3.8B** (not 7B — memory-efficient for t3.medium).

### 4.1 Install Ollama

```bash
# On EC2:
curl https://ollama.ai/install.sh | sh

# Start Ollama service
sudo systemctl start ollama
sudo systemctl enable ollama

# Verify
curl http://localhost:11434/api/tags
```

### 4.2 Pull Phi Model

```bash
# Pull Phi 3.8B (this takes ~2 min on a t3.medium)
ollama pull phi

# Verify
ollama list
# Should show: phi  <model-size>  ...
```

### 4.3 Test Ollama

```bash
# Quick test
curl -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "model": "phi",
    "prompt": "hello",
    "stream": false
  }' | jq .response
```

---

## 5. Terraform / OpenTofu Setup

The IAI agent generates OpenTofu/Terraform code for provisioning.

### 5.1 Install OpenTofu

```bash
# On EC2:
wget https://github.com/opentofu/opentofu/releases/download/v1.7.0/tofu_1.7.0_linux_amd64.zip
unzip tofu_1.7.0_linux_amd64.zip
sudo mv tofu /usr/local/bin/
tofu version
```

### 5.2 Configure Terraform Variables

Create `terraform/staging/terraform.tfvars`:

```hcl
gcp_project = "your-gcp-project-id"
app_tier_ami = "ami-0c55b159cbfafe1f0"  # Ubuntu 22.04 in ap-southeast-5
app_tier_image_uri = "gcr.io/your-project/app:latest"
```

---

## 6. Checkov & Trivy (Security Gate)

These are installed via `requirements.txt`. Verify:

```bash
checkov --version
trivy --version
```

### 6.1 Configure Checkov

No extra setup needed; Checkov runs against Terraform/OpenTofu code.

---

## 7. Infracost (Cost Gate)

### 7.1 Install Infracost

```bash
# On EC2:
curl https://raw.githubusercontent.com/infracost/infracost/master/scripts/install.sh | bash

# Verify
infracost version
```

### 7.2 Get Infracost API Key (Free)

1. Go to https://dashboard.infracost.io
2. Sign up → Get free API key
3. Set environment variable:

```bash
export INFRACOST_API_KEY="<your-key>"
```

---

## 8. Telegram Bot Setup

### 8.1 Create Telegram Bot

1. Open Telegram
2. Search for **@BotFather**
3. `/start` → `/newbot`
4. Follow prompts (name, username)
5. Copy the bot token (format: `123456:ABC-DEF...`)

### 8.2 Set Bot Token

```bash
# On EC2:
export TELEGRAM_BOT_TOKEN="<your-bot-token>"

# Verify
echo $TELEGRAM_BOT_TOKEN
```

---

## 9. Manifest Configuration

The IAI agent reads infrastructure intent from a **manifest** — a self-maintaining YAML file that declares which resources exist, their criticality, dependencies, and cloud assignments.

### 9.1 Edit `manifest.yaml`

Example for staging payments environment:

```yaml
environments:
  staging:
    region: ap-southeast-5
    tags:
      environment: staging
      owner: payments-team
    resources:
      payments_db:
        type: rds_postgres
        cloud: aws
        criticality: critical
        data_bearing: true
        depends_on: []
      app_tier:
        type: ec2
        cloud: aws
        criticality: critical
        depends_on: [payments_db]
      export_bucket:
        type: gcs_bucket
        cloud: gcp
        criticality: high
        depends_on: [payments_db]
```

---

## 10. Run the Agent

### 10.1 Start Telegram Bot

```bash
# In iai-demo directory with venv activated:
source venv/bin/activate
export TELEGRAM_BOT_TOKEN="<your-token>"
export OLLAMA_URL="http://localhost:11434/api/generate"
export OLLAMA_MODEL="phi"
export IAI_MANIFEST="manifest.yaml"

python3 -m bot.telegram_bot
```

**Expected output:**
```
INFO:__main__:IAI bot polling…
```

### 10.2 Send Test Intent via Telegram

1. Open your Telegram bot (search by username)
2. Send:
   ```
   Staging environment: payments Postgres (critical, data-bearing), 
   app tier EC2, export bucket in GCP.
   ```

3. **Bot response:**
   - Ollama processes intent (60 sec timeout)
   - Security gate runs (Checkov + Trivy)
   - Cost gate runs (Infracost)
   - Approval card appears with **[Approve] [Decline]** buttons

### 10.3 Click Approve → Apply

When you click **Approve**:
1. Agent snapshots infrastructure state
2. Creates data-bearing resource snapshots (RDS)
3. Runs `terraform apply` / `tofu apply`
4. Updates manifest with applied state
5. Sends confirmation: "✓ Infrastructure applied successfully. Manifest updated."

---

## 11. Monitoring Dashboard (Optional)

A Flask web dashboard helps troubleshoot during the demo.

### 11.1 Start Monitor Dashboard

```bash
# In a separate terminal (same EC2):
source venv/bin/activate
python3 monitor.py
```

**Access:**
- Browser: `http://<ec2-public-ip>:8000`
- Shows: Agent status, Ollama health, real-time logs, error counts, restart buttons

---

## 12. Troubleshooting

### Issue: `ggml_aligned_malloc: insufficient memory`
**Cause:** Phi model is too large for instance type.  
**Fix:** Upgrade EC2 from `t3.small` → `t3.medium` (4 GB RAM).

### Issue: "Ollama request failed (HTTPConnectionPool... Read timed out)"
**Cause:** Phi takes 60+ seconds on slow instances.  
**Workaround:** Increase timeout in `bot/intent_handler.py` line 90:
```python
timeout=120,  # was 60
```

### Issue: `Error acquiring the state lock`
**Cause:** Previous `terraform apply` interrupted, lock file not cleaned.  
**Fix:**
```bash
rm -f terraform/staging/.terraform.lock.hcl
```

### Issue: Approve button click doesn't trigger apply
**Cause:** Callback handler not registered or async error in `handle_approval`.  
**Debug:**
```bash
# Check logs for errors
tail -50 /tmp/iai-agent.log | grep -i "error\|apply"

# Restart bot with verbose logging
python3 -m bot.telegram_bot 2>&1 | tee bot.log
```

### Issue: WIF authentication fails
**Cause:** WIF pool not properly configured or service account lacks permissions.  
**Fix:** Verify in GCP console:
1. Workload Identity Pools → check AWS account ID mapping
2. Service Account → check IAM bindings include your EC2 role
3. Run: `gcloud auth application-default print-access-token` (should succeed)

---

## 13. End-to-End Demo Workflow

1. **Start services:**
   ```bash
   # Terminal 1: Ollama
   sudo systemctl status ollama
   
   # Terminal 2: Bot
   source venv/bin/activate
   python3 -m bot.telegram_bot
   
   # Terminal 3: Monitor (optional)
   python3 monitor.py
   ```

2. **Send intent via Telegram:** "Set up payments staging: critical Postgres in AWS, app tier, export bucket in GCP."

3. **Monitor output:** Approval card appears in 60–90 seconds (Phi processing time).

4. **Click Approve:** Watch infrastructure build in the logs and on AWS/GCP consoles.

5. **Verify manifest updated:** Check `manifest.yaml` for new resource state entries.

---

## 14. Performance & UX Tuning (for Video)

- **Phi timeout:** Increase to 120s in `intent_handler.py` if frequent timeouts
- **Approval card formatting:** Edit `approval_synthesizer.py` for better line wrapping / labels
- **Log noise:** Set log level to WARNING in `telegram_bot.py` to reduce spam
- **Telegram message edits:** Current code edits the approval card in place (keeps chat clean)

---

## 15. Next Steps

- **Record demo video:** Follow the workflow above on camera
- **Publish on LinkedIn:** Pair with Whitepaper #1 + GTM narrative
- **WP2 (SecOps)** & **WP3 (FinOps):** Follow-up whitepapers
- **Open-source:** Push to GitHub once demo ships

---

## FAQ

**Q: Why `ap-southeast-5` and not `us-east-1`?**  
A: Demonstration of multi-region normalisation. The intent layer abstracts cloud APIs; different regions/clouds all run the same code.

**Q: Can I use Mistral 7B instead of Phi 3.8B?**  
A: Not on t3.medium (memory exhaustion). Phi 3.8B is optimized for resource-constrained environments.

**Q: Why OpenTofu instead of Terraform?**  
A: BSL license — Terraform restricts "competitive" use. OpenTofu is OSI/MPL and drop-in compatible.

**Q: Can the agent approve/apply autonomously?**  
A: Not in v1. Human pushes the button. Progressive autonomy is future work.

---

**Built with:** OpenTofu, Checkov, Trivy, Infracost, Ollama, Telegram, AWS, GCP.

**Questions?** Check logs, then escalate to GitHub Issues.
