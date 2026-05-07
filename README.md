# Hydrus Digital BD — DevOps Assessment

> Production-style web platform on Azure: React · FastAPI · PostgreSQL · Docker · Terraform · AKS · CI/CD

---

## Architecture

```
Browser → DNS → Ingress (NGINX) → AKS
                                   ├── Frontend (React / nginx)  :80
                                   │        ↓ HTTP
                                   ├── Backend (FastAPI)         :8000
                                   │        ↓ asyncpg
                                   └── PostgreSQL               :5432

CI/CD Pipeline → ACR → AKS Rolling Deploy
```

---

## Repository Structure

```
hydrus-devops-assessment/
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── frontend/
│   ├── Dockerfile            # multi-stage: node builder → nginx runtime
│   ├── nginx.conf
│   ├── package.json
│   └── src/
│       ├── index.js
│       ├── index.css
│       ├── App.js
│       └── api.js            # configurable API base URL
├── backend/
│   ├── Dockerfile            # multi-stage: builder → slim runtime
│   ├── requirements.txt
│   └── main.py               # FastAPI app with /health, /health/ready, /api/v1/*
├── terraform/
│   ├── provider.tf
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── environments/
│   │   ├── dev.tfvars
│   │   └── stage.tfvars
│   └── modules/
│       ├── aks/
│       └── acr/
├── k8s/
│   ├── namespace.yaml
│   ├── configmap.yaml
│   ├── secret-example.yaml
│   ├── frontend-deployment.yaml
│   ├── backend-deployment.yaml
│   ├── service.yaml
│   ├── ingress.yaml
│   └── hpa.yaml
├── pipelines/
│   ├── azure-pipelines.yml
│   └── github-actions.yml
└── docs/
    ├── architecture-diagram.png
    ├── monitoring-plan.md
    └── troubleshooting.md
```

---

## Quick Start (Local Docker)

### Prerequisites
- Docker Desktop ≥ 24
- Docker Compose v2

### Run locally

```bash
# 1. Clone repo
git clone https://github.com/<your-org>/hydrus-devops-assessment.git
cd hydrus-devops-assessment

# 2. Set up environment variables
cp .env.example .env
# Edit .env — change POSTGRES_PASSWORD at minimum

# 3. Build and start all services
docker compose up --build

# 4. Access
#   Frontend  →  http://localhost:3000
#   API Docs  →  http://localhost:8000/api/docs
#   Health    →  http://localhost:8000/health
```

### Useful commands

```bash
# Run in background
docker compose up -d --build

# View logs
docker compose logs -f backend
docker compose logs -f frontend

# Stop everything
docker compose down

# Stop and remove volumes (fresh DB)
docker compose down -v

# Start optional pgAdmin
docker compose --profile tools up -d
# → http://localhost:5050  (admin@hydrus.local / admin)

# Rebuild only one service
docker compose build backend
docker compose up -d --no-deps backend
```

---

## Task 1 — Dockerization: Q&A

### Q1. What optimizations did you apply to reduce Docker image size?

**Multi-stage builds** are the primary technique used in both Dockerfiles:

- **Backend**: Stage 1 (`builder`) installs pip packages with build tools (gcc, libpq-dev) into `/install`. Stage 2 (`runtime`) is a clean `python:3.12-slim` image that copies only the compiled packages — no build tools, no cache files.
- **Frontend**: Stage 1 (`builder`) runs `npm ci` and `npm run build` to produce static assets. Stage 2 is a bare `nginx:1.27-alpine` (~40 MB) that only serves the built HTML/CSS/JS.

Additional optimizations:
| Technique | Detail |
|-----------|--------|
| `--no-cache-dir` | pip never writes wheel cache to image layers |
| `--no-install-recommends` | apt installs no suggested packages |
| `rm -rf /var/lib/apt/lists/*` | removes apt index after install |
| `npm ci` instead of `npm install` | deterministic, no dev deps in final image |
| `.dockerignore` | excludes `node_modules`, `.git`, test files from build context |
| `alpine`/`slim` base images | drastically smaller than `debian` or `ubuntu` |
| Non-root user | security best practice, also skips root-owned file overhead |

Result: Backend image ≈ 120 MB (vs ~900 MB without multi-stage). Frontend image ≈ 25 MB.

---

### Q2. What is the difference between a Docker image and a Docker container?

| | Docker Image | Docker Container |
|---|---|---|
| **What** | Read-only, immutable blueprint (like a class definition) | A running instance of an image (like an object) |
| **Storage** | Stored as layered filesystem on disk | Has a thin writable layer on top of image layers |
| **State** | Stateless — never changes after build | Stateful — can write files, hold memory |
| **Lifecycle** | Built once, reused many times | Created, started, stopped, deleted |
| **Command** | `docker build` / `docker pull` | `docker run` / `docker start` |

An analogy: an image is a cookie cutter; containers are the cookies. You can create thousands of identical containers from one image.

---

### Q3. How do you pass environment-specific values to a container securely?

**Never hardcode secrets in Dockerfile or source code.** The correct approaches, ordered by security level:

1. **Runtime environment variables** via `docker run -e` or `docker compose` `.env` file:
   ```bash
   docker run -e DATABASE_URL="postgresql://..." hydrus-backend
   ```
   The `.env` file stays off Git (`.gitignore` entry).

2. **Docker secrets** (Swarm) or **Kubernetes Secrets** (K8s): stored encrypted at rest, mounted as files or env vars inside the container, never logged.

3. **Azure Key Vault** + CSI Driver (production AKS): secrets injected at pod start time from vault, no values in YAML files.

4. **Build-time args (`ARG`)**: used for non-sensitive build customisation (e.g., `REACT_APP_API_URL`). Should NOT be used for passwords — they appear in image history (`docker history`).

The pattern in this project:
- `.env.example` is committed → shows required variables
- `.env` is gitignored → holds actual values locally
- In K8s: `ConfigMap` for non-sensitive config, `Secret` (base64, ideally sealed) for credentials

---

### Q4. How would you troubleshoot a container that exits immediately after startup?

Step-by-step investigation:

```bash
# 1. See the exit code and last status
docker ps -a
# Look for: Exited (1), Exited (137), etc.

# 2. Read the container logs — most common cause visible here
docker logs <container_id>
docker logs <container_id> --tail 50

# 3. If container exits too fast for logs, override the entrypoint
docker run --rm -it --entrypoint sh hydrus-backend
# Now manually run: uvicorn main:app  → see the actual error

# 4. Check for missing environment variables
docker inspect <container_id> | jq '.[0].Config.Env'

# 5. Check exit codes
# Exit 1  → application error (check logs)
# Exit 137 → OOM killed (increase memory limit)
# Exit 139 → segfault
# Exit 143 → SIGTERM (graceful shutdown, usually not a problem)

# 6. Validate the Dockerfile CMD/ENTRYPOINT
docker inspect <image> | jq '.[0].Config.Cmd'

# 7. Check health check failures
docker inspect <container_id> | jq '.[0].State.Health'
```

Common root causes:
- Missing required environment variable (`DATABASE_URL` not set)
- Port already in use on host
- Permission denied on file/socket
- Application crash on startup (import error, syntax error)
- Wrong working directory (`WORKDIR` mismatch)

---

## Task 2 — Terraform Q&A

### Q5. How would you manage separate dev, stage, and prod environments?

Use **Terraform workspaces + environment-specific `.tfvars` files**:

```bash
# Dev
terraform workspace new dev
terraform apply -var-file=environments/dev.tfvars

# Stage
terraform workspace new stage
terraform apply -var-file=environments/stage.tfvars

# Prod
terraform workspace new prod
terraform apply -var-file=environments/prod.tfvars
```

Each `.tfvars` overrides variables like `node_count`, `vm_sku`, `environment_tag`. State is isolated per workspace in the remote backend. For larger teams, a separate storage account per environment is recommended.

---

### Q6. What is Terraform state, and why is remote state important?

**Terraform state** is a JSON file (`terraform.tfstate`) that maps your Terraform configuration to real cloud resources. It tracks resource IDs, metadata, and dependencies so Terraform knows what exists and what needs to change.

**Remote state** (e.g., Azure Blob Storage) is critical because:
- Multiple team members can collaborate without state conflicts
- State is locked during `apply` to prevent concurrent modifications
- State is not lost if a local machine fails
- Sensitive values in state are stored in a managed, access-controlled location

```hcl
# provider.tf
terraform {
  backend "azurerm" {
    resource_group_name  = "hydrus-tf-state-rg"
    storage_account_name = "hydrusstatestorage"
    container_name       = "tfstate"
    key                  = "hydrus.tfstate"
  }
}
```

---

### Q7. How would you secure Terraform state and sensitive variables?

**State security:**
- Azure Blob Storage with **private access** + **versioning** + **soft delete**
- **Azure RBAC**: only CI/CD service principal has `Storage Blob Data Contributor`
- Enable **encryption at rest** (default in Azure)
- Enable **state locking** via Azure Blob lease

**Variable security:**
- Never commit `terraform.tfvars` with real secrets to Git
- Use **Azure Key Vault** as the source of truth; reference in Terraform via `data "azurerm_key_vault_secret"`
- In CI/CD: inject via pipeline secret variables (GitHub Secrets / Azure DevOps Variable Groups)
- Mark sensitive outputs: `sensitive = true` in `outputs.tf`

---

### Q8. What Azure networking/security considerations would you apply for AKS?

| Layer | Consideration |
|-------|---------------|
| **Network plugin** | Azure CNI (not kubenet) for production — pods get real VNet IPs |
| **Private cluster** | AKS API server not exposed to internet; accessed via private endpoint |
| **Network Policy** | Enable Calico/Azure NPM; default-deny all, allow only required pod-to-pod traffic |
| **Ingress** | Single public LoadBalancer for NGINX ingress; backend services as ClusterIP |
| **NSG** | Restrict inbound to port 80/443 only; deny all else at subnet level |
| **ACR integration** | AKS uses managed identity to pull images — no stored credentials |
| **RBAC** | Enable Azure AD integration + Kubernetes RBAC; least-privilege role bindings |
| **Node pools** | System pool (critical pods) separate from user pool (workloads) |
| **Defender for Containers** | Enable Microsoft Defender for runtime threat detection |

---

## Task 3 — Kubernetes Q&A

### Q9. Request flow: Browser → Frontend → Backend API inside AKS

```
1. Browser  →  DNS resolves to Public IP of Azure Load Balancer
2. Load Balancer  →  NGINX Ingress Controller pod (port 80/443)
3. Ingress rules route:
     /          →  frontend-service (ClusterIP :80)
     /api/*     →  backend-service  (ClusterIP :8000)
4. Frontend Service  →  one of 2+ frontend pods (nginx serving React SPA)
5. React app in browser makes XHR to /api/v1/tasks
6. Request goes back through Ingress → backend-service → one of 2+ backend pods
7. Backend pod  →  PostgreSQL StatefulSet pod (ClusterIP :5432)
8. Response flows back through the same chain
```

---

### Q10. Difference between Deployment and StatefulSet

| | Deployment | StatefulSet |
|---|---|---|
| **Use case** | Stateless apps (web, API) | Stateful apps (databases, queues) |
| **Pod identity** | Random names (`pod-abc123`) | Stable, ordered names (`pod-0`, `pod-1`) |
| **Storage** | Shared or no persistent storage | Each pod gets its own PersistentVolume |
| **Scaling** | All pods identical, scale randomly | Ordered scale up/down |
| **DNS** | Single service DNS | Stable per-pod DNS headless service |
| **Example** | Frontend, Backend | PostgreSQL, Kafka, Elasticsearch |

In this assessment: Frontend and Backend use **Deployments**. PostgreSQL uses a **StatefulSet** (or a simple Deployment with a PVC for dev).

---

### Q11. Difference between ClusterIP, NodePort, and LoadBalancer

| Type | Accessible From | Use Case |
|------|----------------|----------|
| **ClusterIP** | Only inside the cluster | Backend services, DB — internal communication |
| **NodePort** | Outside cluster via `<NodeIP>:<Port>` (30000-32767) | Dev/testing; not for production |
| **LoadBalancer** | Internet via cloud provider's LB | Ingress controller, single public-facing service |

In this project: Backend is **ClusterIP** (internal only, accessed via Ingress path routing). NGINX Ingress Controller is **LoadBalancer** (single public IP for all traffic).

---

### Q12. Troubleshoot a pod stuck in CrashLoopBackOff

```bash
# 1. Check pod status and events
kubectl describe pod <pod-name> -n hydrus

# 2. Read logs from the crashing container
kubectl logs <pod-name> -n hydrus
kubectl logs <pod-name> -n hydrus --previous   # logs from last crash

# 3. Check if it's an OOMKill
kubectl describe pod <pod-name> | grep -A5 "OOMKilled"

# 4. Check if environment variables / secrets are missing
kubectl exec -it <pod-name> -n hydrus -- env | grep DATABASE

# 5. Test the image locally
docker run -e DATABASE_URL=... <image>

# 6. Check resource limits — pod may be getting killed
kubectl top pod <pod-name> -n hydrus
```

Common causes: missing env var, wrong DB connection string, OOMKill (memory limit too low), wrong CMD, missing readiness of a dependency.

---

### Q13. How do readiness and liveness probes improve reliability?

| Probe | Question answered | Action on failure |
|-------|-----------------|-------------------|
| **Liveness** | "Is this pod alive?" | Kubernetes **restarts** the container |
| **Readiness** | "Is this pod ready to serve traffic?" | Kubernetes **removes it from Service endpoints** (no traffic) |

In this project:
- **Backend liveness**: `GET /health` — if FastAPI is deadlocked or stuck, the pod gets restarted
- **Backend readiness**: `GET /health/ready` — checks DB connectivity; if DB is down, pod is removed from rotation so users get a proper error rather than 500s
- **Frontend liveness/readiness**: `GET /nginx-health` — ensures nginx is running and serving

This eliminates "running but broken" scenarios and gives zero-downtime deployments: new pods must pass readiness before old pods are terminated.

---

### Q14. Which metrics were used for HPA and why?

**CPU utilization** was used as the primary HPA metric:
```yaml
metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 60
```

**Why 60% CPU?**
- Provides headroom before saturation (allows spike absorption)
- FastAPI is CPU-bound for request parsing and serialization
- Safe threshold: scales out before latency degrades, scales in slowly to avoid flapping

For production, **custom metrics** would be added:
- `http_requests_per_second` (from Prometheus via KEDA) — more accurate for web workloads
- `http_request_duration_seconds_p99` — scale when latency degrades

---

## Task 4 — CI/CD Q&A

### Q15. CI vs CD

| | CI (Continuous Integration) | CD (Continuous Delivery/Deployment) |
|---|---|---|
| **Goal** | Verify code quality and correctness | Deliver verified code to environments |
| **Triggers** | Every push / PR | After CI passes |
| **Actions** | Build, test, lint, scan | Package, push image, deploy to AKS |
| **Output** | Pass/fail signal | Running application |

**CI** in this pipeline: `docker build` → unit tests → SonarQube scan → Trivy vulnerability scan → push to ACR.  
**CD** in this pipeline: `kubectl apply` / `helm upgrade` → readiness check → smoke test → rollback on failure.

---

### Q16. Rollback strategy for a failed deployment

```bash
# Option 1 — Kubernetes rollout (immediate)
kubectl rollout undo deployment/backend -n hydrus
kubectl rollout status deployment/backend -n hydrus

# Option 2 — Roll back to specific revision
kubectl rollout history deployment/backend -n hydrus
kubectl rollout undo deployment/backend --to-revision=3 -n hydrus

# Option 3 — Re-deploy last known good image tag from ACR
kubectl set image deployment/backend \
  backend=hydrusacr.azurecr.io/backend:v1.2.3 -n hydrus
```

In the CI/CD pipeline, automated rollback is triggered by:
1. Readiness probe not passing within `--timeout=5m`
2. Smoke test (curl `/health`) failing post-deploy
3. The pipeline runs `kubectl rollout undo` automatically on failure

---

### Q17. Rolling update vs Blue-Green deployment

| | Rolling Update | Blue-Green |
|---|---|---|
| **How** | Replaces pods one by one | Two full environments; switch traffic all at once |
| **Downtime** | Zero (if probes configured) | Zero |
| **Resource cost** | Low (only extra pods during update) | High (2× infrastructure during switch) |
| **Rollback** | `kubectl rollout undo` (seconds) | Flip DNS/load balancer back (seconds) |
| **Risk** | Both old and new version run simultaneously | Only one version active at a time |
| **Use case** | Most web applications | Critical financial/banking systems |

This project uses **rolling update** (Kubernetes default). Blue-green would use two Deployments and an Ingress/Service switch.

---

### Q18. Protecting pipeline secrets

| Method | Implementation |
|--------|---------------|
| **GitHub Secrets** | `secrets.ACR_PASSWORD` injected as env var, never printed in logs |
| **Azure DevOps Variable Groups** | Linked to Key Vault; values masked in logs |
| **Azure Managed Identity** | AKS node pool pulls ACR images without any stored credential |
| **OIDC Federation** | GitHub Actions authenticates to Azure with short-lived token — no stored service principal password |
| **Secret scanning** | `git-secrets` / GitHub Advanced Security blocks accidental commits |

Never use `echo $SECRET` in pipeline steps — logs are often retained and accessible to team members.

---

## Task 5 — Monitoring, Logging & Troubleshooting

See [`docs/monitoring-plan.md`](docs/monitoring-plan.md) and [`docs/troubleshooting.md`](docs/troubleshooting.md) for full details.

### Production Incident: High response time + 503 errors + pod restarts + high CPU

**Q19. Possible root causes:**
1. Memory leak causing OOMKill → restart loop
2. Unoptimized DB queries holding connections → connection pool exhaustion
3. Missing DB index → slow queries under load
4. Insufficient pod replicas → overloaded pods → timeouts → 503
5. HPA not scaling fast enough (scale-up lag)
6. Ingress controller reaching connection limit
7. PostgreSQL hitting `max_connections`

**Q20. Investigation process:**

```bash
# Step 1 — Identify affected pods
kubectl get pods -n hydrus
kubectl describe pod <crashing-pod> -n hydrus

# Step 2 — Check resource usage
kubectl top pods -n hydrus
kubectl top nodes

# Step 3 — Check recent events
kubectl get events -n hydrus --sort-by='.lastTimestamp'

# Step 4 — Read application logs
kubectl logs <pod-name> -n hydrus --since=30m
kubectl logs <pod-name> -n hydrus --previous

# Step 5 — Check HPA status
kubectl get hpa -n hydrus
kubectl describe hpa backend-hpa -n hydrus

# Step 6 — Check DB connections (exec into backend pod)
kubectl exec -it <backend-pod> -n hydrus -- \
  python -c "import asyncpg; print('pool check')"

# Step 7 — Check Ingress errors
kubectl logs -n ingress-nginx deploy/ingress-nginx-controller --since=15m | grep 503
```

**Q21. Key commands:**

```bash
# Kubernetes
kubectl get pods -n hydrus -o wide
kubectl describe pod <name> -n hydrus
kubectl logs <pod> -n hydrus --previous
kubectl top pods -n hydrus
kubectl rollout restart deployment/backend -n hydrus

# Azure
az aks get-credentials --resource-group hydrus-rg --name hydrus-aks
az monitor metrics list --resource <aks-resource-id> --metric "cpuUsagePercentage"
az monitor log-analytics query -w <workspace-id> --analytics-query "..."

# Linux (inside pod)
kubectl exec -it <pod> -- bash
top
netstat -anp | grep ESTABLISHED | wc -l
cat /proc/meminfo
```

**Q22. Logs and metrics to check first:**
1. `kubectl top pods` — which pod is CPU/memory hot
2. Application logs — error messages, stack traces
3. Prometheus: `http_request_duration_seconds_p99`, `http_requests_total{status="503"}`
4. Grafana dashboard: pod restart count, CPU throttling, memory usage
5. PostgreSQL slow query log: `pg_stat_statements`

**Q23. Immediate mitigation:**
```bash
# Scale out replicas manually
kubectl scale deployment/backend --replicas=6 -n hydrus

# Restart unhealthy pods
kubectl rollout restart deployment/backend -n hydrus

# If DB is the bottleneck — increase connection pool max in env config
# If OOMKill — temporarily increase memory limit
kubectl set resources deployment/backend \
  --limits=memory=512Mi -n hydrus
```

**Q24. Long-term preventive actions:**
1. Set proper `resources.requests` and `resources.limits` on all pods
2. Add DB query profiling (`pg_stat_statements`), optimize slow queries, add indexes
3. Enable HPA with both CPU and custom RPS metrics (via KEDA)
4. Configure PodDisruptionBudget to ensure minimum availability during updates
5. Implement circuit breaker pattern (retry with backoff) in frontend
6. Set up proactive alerts in Grafana (P99 latency > 500ms, error rate > 1%)
7. Load test with k6 before each release to catch regressions

---

## Submission Checklist

| Item | Status |
|------|--------|
| Git repository | ✅ |
| README with setup/deployment steps | ✅ |
| Dockerfile(s) and docker-compose.yml | ✅ |
| Terraform code | ✅ |
| Kubernetes manifests | ✅ |
| CI/CD pipeline YAML | ✅ |
| Architecture diagram | ✅ |
| All 24 questions answered | ✅ |
| Monitoring & troubleshooting docs | ✅ |