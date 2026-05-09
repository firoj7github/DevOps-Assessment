# Hydrus — Deployment Guide

এই guide follow করলে local থেকে শুরু করে Azure production পর্যন্ত
সম্পূর্ণ deploy করা যাবে। প্রতিটা phase এ কী করতে হবে এবং কেন —
সব এখানে আছে।

---

## এক নজরে পুরো flow

```
তোমার machine (Local Dev)
        │
        │  docker compose up
        ▼
Docker Compose — backend + frontend + postgres একসাথে চলে
        │
        │  Azure setup করো
        ▼
Terraform — Azure তে AKS + ACR + Key Vault তৈরি হয়
        │
        │  SonarQube Service Connection বানাও
        ▼
SonarQube — Azure DevOps এ connect করো (Cloud বা Self-hosted)
        │
        │  code push করো
        ▼
Azure DevOps Pipeline — auto build → scan → deploy → rollback
        │
        ▼
AKS (Production) — https://hydrus.example.com
```

---

## প্রয়োজনীয় tools

নিচের সব tool install থাকতে হবে শুরুর আগে।

| Tool | Minimum Version | Download |
|------|----------------|---------|
| Docker Desktop | 24+ | https://docker.com/products/docker-desktop |
| Docker Compose | v2 (Docker Desktop এ built-in) | — |
| Azure CLI | 2.57+ | https://learn.microsoft.com/cli/azure/install |
| Terraform | 1.7+ | https://developer.hashicorp.com/terraform/install |
| kubectl | 1.29+ | https://kubernetes.io/docs/tasks/tools |

Install যাচাই করো:
```bash
docker --version
az --version
terraform --version
kubectl version --client
```

---

## Phase 1 — Local Development (Docker Compose)

**কখন করবে:** নতুন feature বানানোর সময়, দ্রুত test করতে।  
**কী হয়:** backend + frontend + postgres তোমার machine এ চলে।

### ধাপ ১ — Repository clone করো

```bash
git clone https://github.com/<your-org>/hydrus-devops.git
cd hydrus-devops
```

### ধাপ ২ — Environment file তৈরি করো

```bash
cp .env.example .env
```

`.env` file খুলে এই value টা বদলাও (বাকিগুলো default রাখতে পারো):
```
POSTGRES_PASSWORD=তোমার_পছন্দের_password
```

### ধাপ ৩ — সব service চালু করো

```bash
docker compose up --build
```

প্রথমবার চালালে image build হবে — ২-৩ মিনিট লাগতে পারে।

### ধাপ ৪ — Browser এ দেখো

| কী | URL |
|----|-----|
| Frontend (React app) | http://localhost:3000 |
| Backend API Docs | http://localhost:8000/api/docs |
| Health Check | http://localhost:8000/health |
| pgAdmin (database UI) | http://localhost:5050 |

### দরকারি commands

```bash
# Background এ চালাও (terminal বন্ধ করলেও চলতে থাকবে)
docker compose up -d --build

# Log দেখো
docker compose logs -f backend
docker compose logs -f frontend

# শুধু backend rebuild করো (frontend বন্ধ না করে)
docker compose build backend
docker compose up -d --no-deps backend

# সব বন্ধ করো (database data রেখে দাও)
docker compose down

# সব বন্ধ করো + database মুছে ফেলো (fresh start)
docker compose down -v
```

---

## Phase 2 — Azure Infrastructure (Terraform)

**কখন করবে:** প্রথমবার Azure তে setup করার সময় (একবারই করতে হবে)।  
**কী হয়:** Terraform স্বয়ংক্রিয়ভাবে AKS cluster, Container Registry, Key Vault তৈরি করে।

### ধাপ ১ — Azure এ login করো

```bash
az login
```

Browser খুলবে, Microsoft account দিয়ে login করো।

```bash
# সঠিক subscription select করো
az account list --output table
az account set --subscription "<তোমার SUBSCRIPTION_ID>"
```

### ধাপ ২ — Terraform state storage তৈরি করো

> এটা **একবারই** করতে হবে। Terraform এর state file এখানে save থাকবে।

```bash
# Resource group তৈরি করো
az group create \
  --name hydrus-tf-state-rg \
  --location eastus

# Storage account তৈরি করো
az storage account create \
  --name hydrusstatestorage \
  --resource-group hydrus-tf-state-rg \
  --sku Standard_LRS

# Container তৈরি করো
az storage container create \
  --name tfstate \
  --account-name hydrusstatestorage
```

### ধাপ ৩ — Infrastructure deploy করো

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

> `-reconfigure` flag দিতে হয় কারণ একই folder থেকে আলাদা environment এ switch হচ্ছে।

### ধাপ ৪ — Output থেকে values নোট করো

```bash
terraform output acr_login_server    # যেমন: hydrusacr.azurecr.io
terraform output aks_cluster_name    # যেমন: hydrus-aks
terraform output resource_group_name # যেমন: hydrus-rg
```

এই values গুলো Phase 4 এ লাগবে।

### ধাপ ৫ — Key Vault এ production secret রাখো

> Pipeline এ secret YAML এ থাকে না — Key Vault থেকে আসে।
> এতে password কোথাও লেখা থাকে না, pipeline নিজেই নিয়ে নেয়।

Key Vault setup করার দুটো উপায় আছে।
Azure Portal দিয়ে করা সবচেয়ে সহজ।

---

#### Azure Portal দিয়ে Key Vault তৈরি করো

**১. Azure Portal এ যাও**

Browser এ যাও: https://portal.azure.com
তোমার Microsoft account দিয়ে login করো।

---

**২. Key Vault খোঁজো**

উপরে search bar এ লেখো: `Key vaults`
ফলাফলে **Key vaults** এ click করো।

---

**৩. নতুন Key Vault তৈরি করো**

**+ Create** button এ click করো।

এরকম একটা form আসবে — নিচের মতো fill করো:

| Field | Value |
|-------|-------|
| Subscription | তোমার subscription select করো |
| Resource group | `hydrus-rg` (Terraform এ যেটা তৈরি হয়েছে) |
| Key vault name | `hydrus-kv` (globally unique হতে হবে) |
| Region | তোমার AKS এর একই region দাও (যেমন: East US) |
| Pricing tier | Standard |

বাকি সব default রেখে **Review + create** → **Create** click করো।

> Key Vault নাম globally unique হতে হবে।
> `hydrus-kv` taken থাকলে `hydrus-kv-2025` বা অন্য নাম দাও।
> যে নামই দাও, সেটা পরে Variable Group এ `KEY_VAULT_NAME` এ দিতে হবে।

---

**৪. Key Vault এ যাও**

Create হয়ে গেলে **Go to resource** button এ click করো।

---

#### Azure Portal দিয়ে Secret যোগ করো

**৫. Secrets এ যাও**

বাম দিকে menu তে **Objects** section এ **Secrets** এ click করো।

---

**৬. DB_USER secret তৈরি করো**

**+ Generate/Import** button এ click করো।

এরকম form আসবে:

| Field | Value |
|-------|-------|
| Upload options | Manual |
| Name | `DB-USER` |
| Secret value | `hydrus` |
| Enabled | Yes (default) |

**Create** click করো।

---

**৭. DB_PASSWORD secret তৈরি করো**

আবার **+ Generate/Import** click করো।

| Field | Value |
|-------|-------|
| Upload options | Manual |
| Name | `DB-PASSWORD` |
| Secret value | তোমার strong password (যেমন: `Hydr@s2025!Secure`) |
| Enabled | Yes (default) |

**Create** click করো।

> Password এ বড় হাতের অক্ষর + ছোট হাতের অক্ষর + সংখ্যা + বিশেষ চিহ্ন রাখো।
> এই password টা মনে রাখার দরকার নেই — pipeline নিজেই নেবে।

---

**৮. Secret সঠিকভাবে তৈরি হয়েছে কিনা দেখো**

Secrets list এ দুটো item দেখাবে:

```
● DB-PASSWORD     Enabled
● DB-USER         Enabled
```

---

#### Pipeline কে Key Vault access দাও

Key Vault তৈরি হয়েছে, কিন্তু pipeline এখনো এটা read করতে পারবে না।
Azure DevOps Service Principal কে permission দিতে হবে।

**৯. Access policies এ যাও**

Key Vault এর বাম menu তে **Access policies** এ click করো।

---

**১০. Pipeline এর permission যোগ করো**

**+ Create** button এ click করো।

**Permissions tab:**

| Permission type | Value |
|----------------|-------|
| Secret permissions | **Get**, **List** এ tick দাও |

**Next** click করো।

**Principal tab:**

Search box এ তোমার Azure DevOps Service Connection এর নাম লেখো।
সেটা select করো।

> Service Connection এর নাম জানতে:
> Azure DevOps → Project Settings → Service Connections → `hydrus-azure-sc` → details এ
> "Service Principal" নামটা দেখাবে।

**Next** → **Next** → **Create** click করো।

---

**১১. Verify করো — Pipeline access আছে কিনা**

Access policies list এ তোমার Service Principal দেখাবে:

```
hydrus-azure-sc-xxxx    Get, List    (Secret permissions)
```

---

#### সব ঠিক আছে কিনা final check করো

নিচের command টা run করো — secret পাওয়া গেলে setup সঠিক:

```bash
# Azure CLI দিয়ে test করো
az keyvault secret show \
  --vault-name hydrus-kv \
  --name DB-USER \
  --query value \
  --output tsv

# Output দেখাবে: hydrus
```

এই output দেখলে Key Vault সঠিকভাবে কাজ করছে।
Pipeline এখন এই secret নিজেই নিতে পারবে।

---

#### Variable Group এ KEY_VAULT_NAME যোগ করতে ভুলো না

Phase 4 এ Variable Group এ এই variable টা দিতে হবে:

| Variable | Value |
|----------|-------|
| `KEY_VAULT_NAME` | `hydrus-kv` (তোমার Key Vault এর নাম) |

---

## Phase 3 — SonarQube Setup

**কখন করবে:** Azure DevOps pipeline connect করার আগে।  
**কী হয়:** SonarQube code quality scan করে — bug, vulnerability, code smell ধরে।  
Pipeline এ `SonarQube: 'SonarQube_Service_Connection'` এই নামে connection খোঁজে।
সেটা না থাকলে Stage 1 fail করবে।

SonarQube দুইভাবে use করা যায় — যেকোনো একটা বেছে নাও:

```
Option A — SonarQube Cloud (সহজ, free tier আছে)
Option B — Self-hosted SonarQube (নিজের server এ)
```

---

### Option A — SonarQube Cloud (Recommended)

#### ধাপ ১ — SonarQube Cloud account তৈরি করো

1. https://sonarcloud.io এ যাও
2. **Sign up with Azure DevOps** এ click করো
3. তোমার Azure DevOps account দিয়ে login করো
4. Organization তৈরি করো — নাম দাও (যেমন `hydrus-org`)

#### ধাপ ২ — Project তৈরি করো

SonarCloud dashboard এ:

1. **+** → **Analyze new project** এ click করো
2. তোমার Azure DevOps repo select করো
3. **Set Up** click করো
4. Project key নোট করো — এটা pipeline এ লাগবে:
   ```
   Project Key: hydrus-devops-assessment
   ```

#### ধাপ ৩ — Token তৈরি করো

1. SonarCloud → উপরে ডানে তোমার profile icon → **My Account**
2. **Security** tab → **Generate Tokens**
3. Token নাম দাও: `azure-devops-token`
4. **Generate** click করো
5. Token copy করে রাখো — এটা একবারই দেখা যাবে:
   ```
   Token: sqp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

#### ধাপ ৪ — Azure DevOps এ Service Connection তৈরি করো

Azure DevOps → **Project Settings** → **Service Connections** → **New Service Connection**

1. Search করো: **SonarQube** → Select করো → **Next**
2. নিচের মতো fill করো:

   | Field | Value |
   |-------|-------|
   | Server Url | `https://sonarcloud.io` |
   | Token | উপরে copy করা token |
   | Service connection name | `SonarQube_Service_Connection` |

   > ⚠️ নামটা **হুবহু** `SonarQube_Service_Connection` দিতে হবে — pipeline এ এই নামই আছে।

3. **Verify and Save** click করো

#### ধাপ ৫ — Pipeline এ Project Key নিশ্চিত করো

`pipelines/azure-pipelines.yml` এ এই line টা দেখো:
```yaml
cliProjectKey: 'hydrus-devops-assessment'
```
SonarCloud এ তোমার project key যদি আলাদা হয়, এখানে বদলে নাও।

---

### Option B — Self-Hosted SonarQube

নিজের server বা Azure VM তে SonarQube চালাতে চাইলে এই option।

#### ধাপ ১ — SonarQube Server চালু করো

Docker দিয়ে সবচেয়ে সহজ:

```bash
# SonarQube + database চালু করো
docker run -d \
  --name sonarqube \
  -p 9000:9000 \
  -e SONAR_ES_BOOTSTRAP_CHECKS_DISABLE=true \
  sonarqube:community

# Server ready হতে ১-২ মিনিট লাগে
# http://localhost:9000 এ যাও
```

> Azure VM তে চালালে port 9000 inbound rule খুলে দাও NSG তে।

#### ধাপ ২ — First-time login ও password বদলাও

1. Browser এ যাও: `http://<server-ip>:9000`
2. Login: username `admin`, password `admin`
3. নতুন password set করতে বলবে — বদলে নাও

#### ধাপ ৩ — Project তৈরি করো

1. **Projects** → **Create Project** → **Manually**
2. Project display name: `Hydrus`
3. Project key: `hydrus-devops-assessment`
4. **Set Up** click করো

#### ধাপ ৪ — Token তৈরি করো

1. উপরে ডানে profile icon → **My Account** → **Security**
2. Token নাম: `azure-pipeline-token`
3. Type: **Global Analysis Token**
4. **Generate** → token copy করো:
   ```
   Token: sqp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

#### ধাপ ৫ — Azure DevOps এ Service Connection তৈরি করো

Azure DevOps → **Project Settings** → **Service Connections** → **New Service Connection**

1. **SonarQube** select করো → **Next**
2. Fill করো:

   | Field | Value |
   |-------|-------|
   | Server Url | `http://<তোমার-server-ip>:9000` |
   | Token | উপরে copy করা token |
   | Service connection name | `SonarQube_Service_Connection` |

   > ⚠️ নামটা **হুবহু** `SonarQube_Service_Connection` দিতে হবে।

3. **Verify and Save** click করো

---

### Verify — SonarQube কাজ করছে কিনা দেখো

Pipeline এর Stage 1 run হওয়ার পর:

**SonarCloud (Option A):**
```
https://sonarcloud.io/project/overview?id=hydrus-devops-assessment
```

**Self-hosted (Option B):**
```
http://<server-ip>:9000/dashboard?id=hydrus-devops-assessment
```

এরকম dashboard দেখাবে:

```
Quality Gate: ✅ Passed
Bugs:         0
Vulnerabilities: 0
Code Smells:  3
Coverage:     —
```

---

## Phase 4 — CI/CD Pipeline Setup (Azure DevOps)

**কখন করবে:** প্রথমবার pipeline setup করার সময় (একবারই করতে হবে)।  
**কী হয়:** এরপর থেকে code push করলেই auto build → scan → deploy হবে।

### ধাপ ১ — Service Connection তৈরি করো

Azure DevOps → **Project Settings** → **Service Connections** → **New Service Connection**

**দুটো connection বানাতে হবে:**

**Connection ১ — Azure Resource Manager:**
- Type: Azure Resource Manager
- Authentication: Service Principal (recommended)
- Subscription: তোমার subscription select করো
- **Name:** `hydrus-azure-sc` ← এই নামটা ঠিক রাখো

**Connection ২ — Azure Container Registry:**
- Type: Docker Registry → Azure Container Registry
- তোমার ACR select করো
- **Name:** `hydrus-acr-sc` ← এই নামটা ঠিক রাখো

### ধাপ ২ — Variable Group তৈরি করো

Azure DevOps → **Pipelines** → **Library** → **+ Variable Group**

**Group নাম:** `hydrus-vg`

নিচের variables যোগ করো:

| Variable নাম | Value (তোমার actual value দাও) |
|-------------|-------------------------------|
| `AZURE_SERVICE_CONNECTION` | `hydrus-azure-sc` |
| `AZURE_CONTAINER_REGISTRY_SERVICE_CONNECTION` | `hydrus-acr-sc` |
| `ACR_LOGIN_SERVER` | `hydrusacr.azurecr.io` |
| `ACR_NAME` | `hydrusacr` |
| `AKS_CLUSTER_NAME` | `hydrus-aks` |
| `AKS_RESOURCE_GROUP` | `hydrus-rg` |
| `KEY_VAULT_NAME` | `hydrus-kv` |

> `DB_USER` এবং `DB_PASSWORD` এখানে দিতে হবে না — pipeline Key Vault থেকে নিজেই নেবে।

### ধাপ ৩ — Pipeline link করো

Azure DevOps → **Pipelines** → **New Pipeline**  
→ **Azure Repos Git** → তোমার repo select করো  
→ **Existing Azure Pipelines YAML file**  
→ Path: `pipelines/azure-pipelines.yml`  
→ **Save and Run**

### ধাপ ৪ — Pipeline কীভাবে কাজ করে

```
main বা develop branch এ push
            │
            ▼
┌─────────────────────────────────┐
│  Stage 1: Code Quality          │
│                                 │
│  SonarQube code scan করে        │
│  bug, vulnerability, code smell │
│  report দেয়                     │
└────────────────┬────────────────┘
                 │ Pass হলে
                 ▼
┌─────────────────────────────────┐
│  Stage 2: Build & Push          │
│                                 │
│  1. Image tag বানায়             │
│     (branch-shortsha)           │
│     যেমন: main-a1b2c3d4         │
│                                 │
│  2. Backend Docker image build  │
│  3. Trivy security scan         │
│     CRITICAL/HIGH পেলে fail     │
│  4. ACR তে push                 │
│                                 │
│  5. Frontend ও একইভাবে          │
│                                 │
│  6. Scan report save হয়         │
│     (Artifacts tab এ দেখা যাবে) │
└────────────────┬────────────────┘
                 │ Pass হলে
                 │ (PR এ এই stage চলে না)
                 ▼
┌─────────────────────────────────┐
│  Stage 3: Deploy to AKS         │
│                                 │
│  1. AKS credentials নেয়         │
│  2. Key Vault থেকে DB secret    │
│     এনে K8s এ inject করে        │
│  3. K8s manifest apply করে      │
│  4. Pod ready হওয়া পর্যন্ত      │
│     অপেক্ষা করে                 │
│  5. Health check করে            │
│     /health → 200 OK?           │
│                                 │
│  ✅ সফল → Deploy complete        │
│  ❌ Fail → Auto rollback         │
│           আগের version ফিরে আসে │
└─────────────────────────────────┘
```

**PR (Pull Request) এ শুধু Stage 1 + Stage 2 চলে — AKS তে deploy হয় না।**

---

## Rollback

### Auto Rollback (Pipeline)
Smoke test fail করলে pipeline নিজেই আগের version এ ফিরে যায়। কিছু করতে হয় না।

### Manual Rollback (হাতে করতে হলে)

```bash
# AKS credentials নাও
az aks get-credentials \
  --resource-group hydrus-rg \
  --name hydrus-aks \
  --overwrite-existing

# আগের version এ ফিরে যাও
kubectl rollout undo deployment/hydrus-backend -n hydrus
kubectl rollout undo deployment/hydrus-frontend -n hydrus

# Deploy history দেখো
kubectl rollout history deployment/hydrus-backend -n hydrus

# নির্দিষ্ট revision এ ফিরে যাও
kubectl rollout undo deployment/hydrus-backend --to-revision=2 -n hydrus

# নির্দিষ্ট image দিয়ে deploy করো
kubectl set image deployment/hydrus-backend \
  backend=hydrusacr.azurecr.io/hydrus-backend:main-a1b2c3d4 \
  -n hydrus
```

---

## সমস্যা হলে কী করবে

| সমস্যা | কারণ | সমাধান |
|--------|------|---------|
| `ImagePullBackOff` (local K8s) | `imagePullPolicy: Always` কিন্তু local image নেই | `backend-deployment.yaml` use করো (Never policy) |
| `ImagePullBackOff` (AKS) | AKS আর ACR connect না | AKS-ACR integration Terraform এ আছে কিনা দেখো |
| Postgres `CrashLoopBackOff` | DB secret নেই | Key Vault secret set করা হয়েছে কিনা দেখো |
| Ingress থেকে 404 | nginx controller নেই | AKS এ nginx ingress controller install করো |
| Pipeline Stage 2 fail | Trivy CRITICAL vulnerability পেয়েছে | Dockerfile base image update করো |
| Smoke test fail | Pod ready হয়নি | `kubectl get pods -n hydrus` দিয়ে দেখো |
| HPA কাজ করছে না | metrics-server নেই | AKS এ metrics-server enable আছে কিনা দেখো |

---

## সব শেষ করতে (Cleanup)

```bash
# K8s namespace এবং সব resource মুছে ফেলো
kubectl delete namespace hydrus

# Azure infrastructure destroy করো
# সাবধান — এটা irreversible, data মুছে যাবে
cd terraform
terraform destroy -var-file=environments/prod.tfvars
```