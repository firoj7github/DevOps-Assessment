# Deployment Guide — Hydrus DevOps Assessment

## Prerequisites

| Tool | Minimum Version | Purpose |
|------|----------------|---------|
| Docker Desktop / Engine | 24+ | Local container runtime |
| Docker Compose | v2 | Multi-service local dev |
| Terraform | 1.7+ | Azure infrastructure provisioning |
| Azure CLI (`az`) | 2.57+ | Azure authentication & operations |
| kubectl | 1.29+ | Kubernetes cluster management |
| Helm | 3.14+ | (Optional) Chart-based deployment |

---

## Phase 1 — Local Development (Docker Compose)

### 1.1 Clone & Configure

```bash
git clone https://github.com/<your-org>/hydrus-devops-assessment.git
cd hydrus-devops-assessment

# Copy example env and set your own values
cp .env.example .env
# Minimum: change POSTGRES_PASSWORD
```

### 1.2 Build & Start All Services

```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| Frontend (React) | http://localhost:3000 |
| Backend API Docs | http://localhost:8000/api/docs |
| Health Endpoint | http://localhost:8000/health |
| pgAdmin (optional) | http://localhost:5050 |

### 1.3 Useful Commands

```bash
# Background mode
docker compose up -d --build

# Tail logs
docker compose logs -f backend
docker compose logs -f frontend

# Rebuild one service only
docker compose build backend
docker compose up -d --no-deps backend

# Stop (keep volumes / DB data)
docker compose down

# Stop + wipe volumes (fresh DB)
docker compose down -v

# Start pgAdmin profile
docker compose --profile tools up -d
```

---

## Phase 2 — Azure Infrastructure (Terraform)

### 2.1 Authenticate to Azure

```bash
az login
az account set --subscription "<SUBSCRIPTION_ID>"
```

### 2.2 Create Remote State Backend (one-time)

```bash
az group create --name hydrus-tf-state-rg --location eastus
az storage account create \
  --name hydrusstatestorage \
  --resource-group hydrus-tf-state-rg \
  --sku Standard_LRS
az storage container create \
  --name tfstate \
  --account-name hydrusstatestorage
```

### 2.3 Deploy Infrastructure

```bash
cd terraform

# ── Dev environment ───────────────────────────────────────────────────────────
terraform init -backend-config=environments/dev.backend.hcl
terraform plan -var-file=environments/dev.tfvars -out=dev.plan
terraform apply dev.plan

# ── Stage environment ─────────────────────────────────────────────────────────
terraform init -backend-config=environments/stage.backend.hcl -reconfigure
terraform plan -var-file=environments/stage.tfvars -out=stage.plan
terraform apply stage.plan

# ── Prod environment ──────────────────────────────────────────────────────────
terraform init -backend-config=environments/prod.backend.hcl -reconfigure
terraform plan -var-file=environments/prod.tfvars -out=prod.plan
terraform apply prod.plan
```

> `-reconfigure` flag টা দরকার যখন একই directory থেকে ভিন্ন environment এ switch করা হয়।

### 2.4 Key Outputs

After `apply`, note these outputs:

```bash
terraform output acr_login_server     # e.g. hydrusacr.azurecr.io
terraform output aks_cluster_name
terraform output resource_group_name
terraform output kubeconfig_command   # az aks get-credentials ...
```

---

## Phase 3 — AKS Kubernetes Deployment

### 3.1 Get Cluster Credentials

```bash
# terraform output থেকে সঠিক command নাও
terraform output kubeconfig_command
# অথবা manually:
az aks get-credentials \
  --resource-group $(terraform output -raw resource_group_name) \
  --name $(terraform output -raw aks_cluster_name) \
  --overwrite-existing

kubectl get nodes   # verify connection
```

### 3.2 Build & Push Images to ACR

```bash
ACR=hydrusacr.azurecr.io
TAG=$(git rev-parse --short HEAD)

az acr login --name hydrusacr

# Backend
docker build -t $ACR/hydrus-backend:$TAG ./backend
docker push $ACR/hydrus-backend:$TAG

# Frontend
docker build -t $ACR/hydrus-frontend:$TAG ./frontend
docker push $ACR/hydrus-frontend:$TAG
```

### 3.3 Apply Kubernetes Manifests

```bash
# Apply in dependency order
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret-example.yaml
kubectl apply -f k8s/postgres-statefulset.yaml
kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/service.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/hpa.yaml
```

### 3.4 Verify Deployment

```bash
# Watch rollout status
kubectl rollout status deployment/hydrus-backend -n hydrus
kubectl rollout status deployment/hydrus-frontend -n hydrus

# Check all pods are Running
kubectl get pods -n hydrus

# Get public IP from Ingress
kubectl get ingress -n hydrus

# Manual health check
curl https://hydrus.example.com/health
```

---

## Phase 4 — CI/CD Pipeline (Azure DevOps)

### 4.1 Required Setup in Azure DevOps

1. **Service Connection** → Project Settings → Service Connections → New → Azure Resource Manager
   - Name it to match `$(AZURE_SERVICE_CONNECTION)` in the pipeline YAML

2. **Variable Group** (`hydrus-vg`) → Pipelines → Library → Variable Groups:

| Variable | Example Value |
|----------|--------------|
| `ACR_LOGIN_SERVER` | `hydrusacr.azurecr.io` |
| `ACR_NAME` | `hydrusacr` |
| `AKS_CLUSTER_NAME` | `hydrus-aks` |
| `AKS_RESOURCE_GROUP` | `hydrus-rg` |
| `AZURE_SERVICE_CONNECTION` | `hydrus-azure-sc` |
| `AZURE_CONTAINER_REGISTRY_SERVICE_CONNECTION` | `hydrus-acr-sc` |

3. **Link pipeline YAML** → Pipelines → New Pipeline → Azure Repos Git → select `pipelines/azure-pipelines.yml`

### 4.2 Pipeline Trigger

The pipeline runs automatically on:
- Push to `main` or `develop` (CI + CD)
- Pull Request targeting `main` (CI only — no deploy)

### 4.3 Pipeline Stages Overview

```
Analysis (SonarQube)
    ↓
Build (Docker Build + Trivy Scan + ACR Push)
    ↓
Deploy (AKS Deploy + Smoke Test → auto-rollback on failure)
```

---

## Rollback Procedure

```bash
# Immediate rollback to previous revision
kubectl rollout undo deployment/hydrus-backend -n hydrus
kubectl rollout undo deployment/hydrus-frontend -n hydrus

# Check rollout history
kubectl rollout history deployment/hydrus-backend -n hydrus

# Rollback to a specific revision
kubectl rollout undo deployment/hydrus-backend --to-revision=2 -n hydrus

# Re-deploy a known-good image tag
kubectl set image deployment/hydrus-backend \
  backend=hydrusacr.azurecr.io/hydrus-backend:v1.0.0 -n hydrus
```

---

## Environment Tear-Down

```bash
# Remove K8s resources
kubectl delete namespace hydrus

# Destroy Azure infra (careful — irreversible)
cd terraform
terraform init -backend-config=environments/dev.backend.hcl
terraform destroy -var-file=environments/dev.tfvars
```