# Hydrus — Deployment Guide

Follow this guide to deploy completely from local all the way to Azure production.
What to do at each phase and why — everything is here.

---

## Full Flow at a Glance

```
Your machine (Local Dev)
        │
        │  docker compose up
        ▼
Docker Compose — backend + frontend + postgres run together
        │
        │  Set up Azure
        ▼
Terraform — creates AKS + ACR + Key Vault on Azure
        │
        │  Create SonarQube Service Connection
        ▼
SonarQube — connect to Azure DevOps (Cloud or Self-hosted)
        │
        │  push code
        ▼
Azure DevOps Pipeline — auto build → scan → deploy → rollback
        │
        ▼
AKS (Production) — https://hydrus.example.com
```

---

## Required Tools

All tools below must be installed before starting.

| Tool | Minimum Version | Download |
|------|----------------|---------|
| Docker Desktop | 24+ | https://docker.com/products/docker-desktop |
| Docker Compose | v2 (built-in with Docker Desktop) | — |
| Azure CLI | 2.57+ | https://learn.microsoft.com/cli/azure/install |
| Terraform | 1.7+ | https://developer.hashicorp.com/terraform/install |
| kubectl | 1.29+ | https://kubernetes.io/docs/tasks/tools |

Verify install:
```bash
docker --version
az --version
terraform --version
kubectl version --client
```

---

## Phase 1 — Local Development (Docker Compose)

**When to do this:** When building a new feature, for quick testing.
**What happens:** backend + frontend + postgres run on your machine.

### Step 1 — Clone the Repository

```bash
git clone https://github.com/<your-org>/hydrus-devops.git
cd hydrus-devops
```

### Step 2 — Create Environment File

```bash
cp .env.example .env
```

Open the `.env` file and change this value (you can leave the rest as default):
```
POSTGRES_PASSWORD=your_preferred_password
```

### Step 3 — Start All Services

```bash
docker compose up --build
```

First time running will build the image — may take 2-3 minutes.

### Step 4 — View in Browser

| What | URL |
|----|-----|
| Frontend (React app) | http://localhost:3000 |
| Backend API Docs | http://localhost:8000/api/docs |
| Health Check | http://localhost:8000/health |
| pgAdmin (database UI) | http://localhost:5050 |

### Useful Commands

```bash
# Run in background (keeps running even if terminal is closed)
docker compose up -d --build

# View logs
docker compose logs -f backend
docker compose logs -f frontend

# Rebuild only backend (without stopping frontend)
docker compose build backend
docker compose up -d --no-deps backend

# Stop everything (keep database data)
docker compose down

# Stop everything + delete database (fresh start)
docker compose down -v
```

---

## Phase 2 — Azure Infrastructure (Terraform)

**When to do this:** When setting up on Azure for the first time (only needs to be done once).
**What happens:** Terraform automatically creates AKS cluster, Container Registry, Key Vault.

### Step 1 — Log in to Azure

```bash
az login
```

A browser will open — log in with your Microsoft account.

```bash
# Select the correct subscription
az account list --output table
az account set --subscription "<your SUBSCRIPTION_ID>"
```

### Step 2 — Create Terraform State Storage

> This only needs to be done **once**. Terraform's state file will be saved here.

```bash
# Create resource group
az group create \
  --name hydrus-tf-state-rg \
  --location eastus

# Create storage account
az storage account create \
  --name hydrusstatestorage \
  --resource-group hydrus-tf-state-rg \
  --sku Standard_LRS

# Create container
az storage container create \
  --name tfstate \
  --account-name hydrusstatestorage
```

### Step 3 — Deploy Infrastructure

```bash
cd terraform

# Dev environment
terraform init -backend-config=environments/dev.backend.hcl
terraform plan -var-file=environments/dev.tfvars -out=dev.plan
terraform apply dev.plan

# Stage environment
terraform init -backend-config=environments/stage.backend.hcl -reconfigure
terraform plan -var-file=environments/stage.tfvars -out=stage.plan
terraform apply stage.plan

# Production environment
terraform init -backend-config=environments/prod.backend.hcl -reconfigure
terraform plan -var-file=environments/prod.tfvars -out=prod.plan
terraform apply prod.plan
```

> The `-reconfigure` flag is needed because switching between different environments from the same folder.

### Step 4 — Note Values from Output

```bash
terraform output acr_login_server    # e.g.: hydrusacr.azurecr.io
terraform output aks_cluster_name    # e.g.: hydrus-aks
terraform output resource_group_name # e.g.: hydrus-rg
```

These values will be needed in Phase 4.

### Step 5 — Store Production Secrets in Key Vault

> Secrets don't live in the pipeline YAML — they come from Key Vault.
> This way no passwords are written anywhere; the pipeline fetches them automatically.

There are two ways to set up Key Vault.
Using the Azure Portal is the easiest.

---

#### Create Key Vault via Azure Portal

**1. Go to Azure Portal**

Go to: https://portal.azure.com
Log in with your Microsoft account.

---

**2. Search for Key Vault**

In the search bar at the top, type: `Key vaults`
Click on **Key vaults** in the results.

---

**3. Create a New Key Vault**

Click the **+ Create** button.

A form will appear — fill it in like this:

| Field | Value |
|-------|-------|
| Subscription | Select your subscription |
| Resource group | `hydrus-rg` (the one created by Terraform) |
| Key vault name | `hydrus-kv` (must be globally unique) |
| Region | Use the same region as your AKS (e.g., East US) |
| Pricing tier | Standard |

Leave everything else as default, then click **Review + create** → **Create**.

> Key Vault name must be globally unique.
> If `hydrus-kv` is taken, try `hydrus-kv-2025` or another name.
> Whatever name you use, you'll need to put it in the Variable Group under `KEY_VAULT_NAME` later.

---

**4. Go to the Key Vault**

Once created, click **Go to resource**.

---

#### Add Secrets via Azure Portal

**5. Go to Secrets**

In the left menu, under the **Objects** section, click **Secrets**.

---

**6. Create the DB_USER secret**

Click the **+ Generate/Import** button.

A form will appear:

| Field | Value |
|-------|-------|
| Upload options | Manual |
| Name | `DB-USER` |
| Secret value | `hydrus` |
| Enabled | Yes (default) |

Click **Create**.

---

**7. Create the DB_PASSWORD secret**

Click **+ Generate/Import** again.

| Field | Value |
|-------|-------|
| Upload options | Manual |
| Name | `DB-PASSWORD` |
| Secret value | Your strong password (e.g., `Hydr@s2025!Secure`) |
| Enabled | Yes (default) |

Click **Create**.

> Keep uppercase + lowercase + numbers + special characters in the password.
> No need to remember this password — the pipeline will fetch it automatically.

---

**8. Verify Secrets Were Created Correctly**

The Secrets list will show two items:

```
● DB-PASSWORD     Enabled
● DB-USER         Enabled
```

---

#### Grant Pipeline Access to Key Vault

The Key Vault is created, but the pipeline still can't read it.
You need to give the Azure DevOps Service Principal permission.

**9. Go to Access Policies**

In the Key Vault's left menu, click **Access policies**.

---

**10. Add Pipeline Permission**

Click the **+ Create** button.

**Permissions tab:**

| Permission type | Value |
|----------------|-------|
| Secret permissions | Tick **Get**, **List** |

Click **Next**.

**Principal tab:**

In the search box, type the name of your Azure DevOps Service Connection.
Select it.

> To find the Service Connection name:
> Azure DevOps → Project Settings → Service Connections → `hydrus-azure-sc` → in details
> the "Service Principal" name will be shown.

Click **Next** → **Next** → **Create**.

---

**11. Verify — Check if Pipeline Has Access**

Your Service Principal will appear in the Access Policies list:

```
hydrus-azure-sc-xxxx    Get, List    (Secret permissions)
```

---

#### Final Check — Verify Everything is Working

Run this command — if the secret is retrieved, the setup is correct:

```bash
# Test with Azure CLI
az keyvault secret show \
  --vault-name hydrus-kv \
  --name DB-USER \
  --query value \
  --output tsv

# Output will show: hydrus
```

If you see this output, Key Vault is working correctly.
The pipeline can now fetch these secrets on its own.

---

#### Don't Forget to Add KEY_VAULT_NAME to Variable Group

In Phase 4, you need to add this variable to the Variable Group:

| Variable | Value |
|----------|-------|
| `KEY_VAULT_NAME` | `hydrus-kv` (your Key Vault name) |

---

## Phase 3 — SonarQube Setup

**When to do this:** Before connecting the Azure DevOps pipeline.
**What happens:** SonarQube scans code quality — catches bugs, vulnerabilities, code smells.
The pipeline looks for a connection named `SonarQube: 'SonarQube_Service_Connection'`.
If it's not there, Stage 1 will fail.

SonarQube can be used in two ways — pick one:

```
Option A — SonarQube Cloud (easier, has free tier)
Option B — Self-hosted SonarQube (on your own server)
```

---

### Option A — SonarQube Cloud (Recommended)

#### Step 1 — Create SonarQube Cloud Account

1. Go to https://sonarcloud.io
2. Click **Sign up with Azure DevOps**
3. Log in with your Azure DevOps account
4. Create an Organization — give it a name (e.g., `hydrus-org`)

#### Step 2 — Create a Project

In the SonarCloud dashboard:

1. Click **+** → **Analyze new project**
2. Select your Azure DevOps repo
3. Click **Set Up**
4. Note the project key — you'll need this in the pipeline:
   ```
   Project Key: hydrus-devops-assessment
   ```

#### Step 3 — Create a Token

1. SonarCloud → your profile icon at the top right → **My Account**
2. **Security** tab → **Generate Tokens**
3. Give the token a name: `azure-devops-token`
4. Click **Generate**
5. Copy the token — it will only be shown once:
   ```
   Token: sqp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

#### Step 4 — Create Service Connection in Azure DevOps

Azure DevOps → **Project Settings** → **Service Connections** → **New Service Connection**

1. Search: **SonarQube** → Select → **Next**
2. Fill in as below:

   | Field | Value |
   |-------|-------|
   | Server Url | `https://sonarcloud.io` |
   | Token | The token you copied above |
   | Service connection name | `SonarQube_Service_Connection` |

   > The name must be **exactly** `SonarQube_Service_Connection` — that's what's in the pipeline.

3. Click **Verify and Save**

#### Step 5 — Confirm Project Key in Pipeline

In `pipelines/azure-pipelines.yml`, find this line:
```yaml
cliProjectKey: 'hydrus-devops-assessment'
```
If your project key in SonarCloud is different, update it here.

---

### Option B — Self-Hosted SonarQube

Use this option if you want to run SonarQube on your own server or Azure VM.

#### Step 1 — Start SonarQube Server

Docker makes it easiest:

```bash
# Start SonarQube + database
docker run -d \
  --name sonarqube \
  -p 9000:9000 \
  -e SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true \
  sonarqube:community

# Server takes 1-2 minutes to be ready
# Go to http://localhost:9000
```

> If running on an Azure VM, open port 9000 inbound rule in NSG.

#### Step 2 — First-time Login and Change Password

1. Go to browser: `http://<server-ip>:9000`
2. Login: username `admin`, password `admin`
3. It will ask you to set a new password — change it

#### Step 3 — Create a Project

1. **Projects** → **Create Project** → **Manually**
2. Project display name: `Hydrus`
3. Project key: `hydrus-devops-assessment`
4. Click **Set Up**

#### Step 4 — Create a Token

1. Profile icon at top right → **My Account** → **Security**
2. Token name: `azure-pipeline-token`
3. Type: **Global Analysis Token**
4. **Generate** → copy the token:
   ```
   Token: sqp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

#### Step 5 — Create Service Connection in Azure DevOps

Azure DevOps → **Project Settings** → **Service Connections** → **New Service Connection**

1. Select **SonarQube** → **Next**
2. Fill in:

   | Field | Value |
   |-------|-------|
   | Server Url | `http://<your-server-ip>:9000` |
   | Token | The token you copied above |
   | Service connection name | `SonarQube_Service_Connection` |

   > The name must be **exactly** `SonarQube_Service_Connection`.

3. Click **Verify and Save**

---

### Verify — Check if SonarQube is Working

After Stage 1 of the pipeline runs:

**SonarCloud (Option A):**
```
https://sonarcloud.io/project/overview?id=hydrus-devops-assessment
```

**Self-hosted (Option B):**
```
http://<server-ip>:9000/dashboard?id=hydrus-devops-assessment
```

You'll see a dashboard like this:

```
Quality Gate: Passed
Bugs:         0
Vulnerabilities: 0
Code Smells:  3
Coverage:     —
```

---

## Phase 4 — CI/CD Pipeline Setup (Azure DevOps)

**When to do this:** When setting up the pipeline for the first time (only needs to be done once).
**What happens:** After this, every code push will auto build → scan → deploy.

### Step 1 — Create Service Connection

Azure DevOps → **Project Settings** → **Service Connections** → **New Service Connection**

**You need to create two connections:**

**Connection 1 — Azure Resource Manager:**
- Type: Azure Resource Manager
- Authentication: Service Principal (recommended)
- Subscription: Select your subscription
- **Name:** `hydrus-azure-sc` ← keep this name exact

**Connection 2 — Azure Container Registry:**
- Type: Docker Registry → Azure Container Registry
- Select your ACR
- **Name:** `hydrus-acr-sc` ← keep this name exact

### Step 2 — Create Variable Group

Azure DevOps → **Pipelines** → **Library** → **+ Variable Group**

**Group name:** `hydrus-vg`

Add the following variables:

| Variable Name | Value (enter your actual value) |
|-------------|-------------------------------|
| `AZURE_SERVICE_CONNECTION` | `hydrus-azure-sc` |
| `AZURE_CONTAINER_REGISTRY_SERVICE_CONNECTION` | `hydrus-acr-sc` |
| `ACR_LOGIN_SERVER` | `hydrusacr.azurecr.io` |
| `ACR_NAME` | `hydrusacr` |
| `AKS_CLUSTER_NAME` | `hydrus-aks` |
| `AKS_RESOURCE_GROUP` | `hydrus-rg` |
| `KEY_VAULT_NAME` | `hydrus-kv` |

> `DB_USER` and `DB_PASSWORD` don't need to go here — the pipeline will fetch them from Key Vault automatically.

### Step 3 — Link the Pipeline

Azure DevOps → **Pipelines** → **New Pipeline**
→ **Azure Repos Git** → select your repo
→ **Existing Azure Pipelines YAML file**
→ Path: `pipelines/azure-pipelines.yml`
→ **Save and Run**

### Step 4 — How the Pipeline Works

```
Push to main or develop branch
            │
            ▼
┌─────────────────────────────────┐
│  Stage 1: Code Quality          │
│                                 │
│  SonarQube scans code           │
│  reports bugs, vulnerabilities, │
│  code smells                    │
└────────────────┬────────────────┘
                 │ If Pass
                 ▼
┌─────────────────────────────────┐
│  Stage 2: Build & Push          │
│                                 │
│  1. Creates image tag           │
│     (branch-shortsha)           │
│     e.g.: main-a1b2c3d4         │
│                                 │
│  2. Backend Docker image build  │
│  3. Trivy security scan         │
│     Fails if CRITICAL/HIGH found│
│  4. Push to ACR                 │
│                                 │
│  5. Frontend same process       │
│                                 │
│  6. Scan report saved           │
│     (visible in Artifacts tab)  │
└────────────────┬────────────────┘
                 │ If Pass
                 │ (this stage doesn't run on PRs)
                 ▼
┌─────────────────────────────────┐
│  Stage 3: Deploy to AKS         │
│                                 │
│  1. Gets AKS credentials        │
│  2. Fetches DB secret from      │
│     Key Vault, injects into K8s │
│  3. Applies K8s manifest        │
│  4. Waits until pod is ready    │
│                                 │
│  5. Runs health check           │
│     /health → 200 OK?           │
│                                 │
│  Success → Deploy complete    │
│  Fail → Auto rollback         │
│           Previous version      │
│           restored              │
└─────────────────────────────────┘
```

**On a PR (Pull Request), only Stage 1 + Stage 2 run — nothing deploys to AKS.**

---

## Rollback

### Auto Rollback (Pipeline)
If the smoke test fails, the pipeline automatically reverts to the previous version. Nothing needs to be done.

### Manual Rollback (if you need to do it by hand)

```bash
# Get AKS credentials
az aks get-credentials \
  --resource-group hydrus-rg \
  --name hydrus-aks \
  --overwrite-existing

# Roll back to previous version
kubectl rollout undo deployment/hydrus-backend -n hydrus
kubectl rollout undo deployment/hydrus-frontend -n hydrus

# View deploy history
kubectl rollout history deployment/hydrus-backend -n hydrus

# Roll back to a specific revision
kubectl rollout undo deployment/hydrus-backend --to-revision=2 -n hydrus

# Deploy with a specific image
kubectl set image deployment/hydrus-backend \
  backend=hydrusacr.azurecr.io/hydrus-backend:main-a1b2c3d4 \
  -n hydrus
```

---

## Troubleshooting

| Problem | Cause | Solution |
|--------|------|---------|
| `ImagePullBackOff` (local K8s) | `imagePullPolicy: Always` but local image is missing | Use `backend-deployment.yaml` (Never policy) |
| `ImagePullBackOff` (AKS) | AKS and ACR not connected | Check if AKS-ACR integration is in Terraform |
| Postgres `CrashLoopBackOff` | DB secret missing | Check if Key Vault secret has been set |
| 404 from Ingress | nginx controller missing | Install nginx ingress controller on AKS |
| Pipeline Stage 2 fail | Trivy found CRITICAL vulnerability | Update Dockerfile base image |
| Smoke test fail | Pod not ready | Check with `kubectl get pods -n hydrus` |
| HPA not working | metrics-server missing | Check if metrics-server is enabled on AKS |

---

## Cleanup (When Done with Everything)

```bash
# Delete K8s namespace and all resources
kubectl delete namespace hydrus

# Destroy Azure infrastructure
# Caution — this is irreversible, data will be lost
cd terraform
terraform destroy -var-file=environments/prod.tfvars
```