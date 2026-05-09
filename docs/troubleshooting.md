# Troubleshooting Guide — Hydrus DevOps Assessment

## Quick Reference: Diagnostic Commands

```bash
# Cluster overview
kubectl get all -n hydrus
kubectl get events -n hydrus --sort-by='.lastTimestamp'

# Resource usage
kubectl top pods -n hydrus
kubectl top nodes

# HPA status
kubectl get hpa -n hydrus
kubectl describe hpa -n hydrus
```

---

## Section 1 — Pod in CrashLoopBackOff

### Symptoms
- `kubectl get pods` shows `CrashLoopBackOff` or `Error` status
- Pod restart count keeps increasing

### Step-by-Step Investigation

```bash
# Step 1: Check exit code and last known state
kubectl describe pod <pod-name> -n hydrus
# Look for: "Exit Code", "Last State", "Reason"

# Step 2: Read current logs
kubectl logs <pod-name> -n hydrus

# Step 3: Read logs from the previous (crashed) container
kubectl logs <pod-name> -n hydrus --previous

# Step 4: Check for OOMKill
kubectl describe pod <pod-name> -n hydrus | grep -A5 "OOMKilled"
# If OOMKilled → pod hit memory limit; increase limits temporarily:
kubectl set resources deployment/hydrus-backend \
  --limits=memory=512Mi -n hydrus

# Step 5: Check environment variables / secrets
kubectl exec -it <pod-name> -n hydrus -- env | grep DATABASE

# Step 6: Reproduce locally
docker run -e DATABASE_URL=postgresql://... <image>
```

### Common Root Causes & Fixes

| Exit Code | Cause | Fix |
|-----------|-------|-----|
| `1` | Application error (import fail, missing env) | Check logs; add missing env var |
| `137` | OOMKilled | Increase `resources.limits.memory` |
| `139` | Segfault | Check native library compatibility |
| `143` | SIGTERM (graceful stop) | Usually not a problem; check readiness |

---

## Section 2 — Pod Stuck in Pending

### Symptoms
- `kubectl get pods` shows `Pending` for more than 2 minutes

### Investigation

```bash
kubectl describe pod <pod-name> -n hydrus
# Look at "Events" section at the bottom:
# "Insufficient cpu" → node doesn't have enough CPU
# "Insufficient memory" → node doesn't have enough memory
# "0/3 nodes are available" → all nodes are full or tainted

# Check node capacity
kubectl describe nodes | grep -A5 "Allocated resources"

# Check if PVC is not bound (if pod needs storage)
kubectl get pvc -n hydrus
```

### Fixes

- **Insufficient resources**: scale up node pool via `az aks scale` or reduce pod `resources.requests`
- **Unschedulable taint**: check node taints with `kubectl describe node <node>` and add matching tolerations to pod spec
- **PVC Pending**: ensure the StorageClass exists and the PV is available

---

## Section 3 — High Response Times + 503 Errors

This is the production incident scenario from the assessment.

### Symptoms
- Backend API P99 latency > 500ms
- Users receiving random `503 Service Unavailable`
- Pods restarting frequently
- High CPU during peak traffic

### Step-by-Step Investigation

```bash
# Step 1: Identify affected pods
kubectl get pods -n hydrus -o wide
kubectl describe pod <crashing-pod> -n hydrus

# Step 2: Check resource usage
kubectl top pods -n hydrus
kubectl top nodes

# Step 3: Check recent cluster events
kubectl get events -n hydrus --sort-by='.lastTimestamp' | tail -30

# Step 4: Read application logs (last 30 minutes)
kubectl logs <pod-name> -n hydrus --since=30m
kubectl logs <pod-name> -n hydrus --previous

# Step 5: Check HPA status — is it scaling?
kubectl get hpa -n hydrus
kubectl describe hpa backend-hpa -n hydrus
# "ScalingLimited: True" → already at maxReplicas

# Step 6: Check Ingress controller for 503 errors
kubectl logs -n ingress-nginx deploy/ingress-nginx-controller \
  --since=15m | grep 503

# Step 7: Check DB connections (exec into a backend pod)
kubectl exec -it <backend-pod> -n hydrus -- \
  python -c "import asyncpg; print('DB reachable')"
```

### Possible Root Causes

1. **Memory leak → OOMKill → restart loop** — pod uses progressively more memory until the kernel kills it
2. **DB connection pool exhaustion** — too many concurrent requests, pool at max, new requests queue/timeout
3. **Missing DB index** — slow queries under load hold connections longer
4. **HPA not scaling fast enough** — scale-up lag (default: 15s evaluation period)
5. **Ingress controller connection limit reached** — NGINX worker_connections too low
6. **PostgreSQL `max_connections` hit** — DB refuses new connections → backend 500s

### Immediate Mitigation

```bash
# Scale out replicas manually (bypass HPA temporarily)
kubectl scale deployment/hydrus-backend --replicas=6 -n hydrus

# Restart unhealthy pods (triggers rolling restart)
kubectl rollout restart deployment/hydrus-backend -n hydrus

# Temporarily increase memory limit if OOMKill is the cause
kubectl set resources deployment/hydrus-backend \
  --limits=memory=512Mi -n hydrus

# If DB is the bottleneck — increase connection pool via env var
kubectl set env deployment/hydrus-backend \
  DB_POOL_SIZE=20 DB_MAX_OVERFLOW=10 -n hydrus
```

### Long-Term Fixes

1. Set proper `resources.requests` and `resources.limits` on all pods to allow accurate scheduling
2. Add `pg_stat_statements` to PostgreSQL, profile slow queries, add missing indexes
3. Enable HPA with custom RPS metrics via KEDA (faster response than CPU-based HPA)
4. Configure `PodDisruptionBudget` to ensure minimum availability during rolling updates
5. Implement circuit breaker / retry-with-backoff in frontend (`axios-retry`)
6. Set proactive Grafana alerts (P99 > 300ms, error rate > 0.5%)
7. Run load tests with `k6` before each release

---

## Section 4 — Container Image Fails to Pull (ImagePullBackOff)

### Symptoms
- `kubectl get pods` shows `ImagePullBackOff` or `ErrImagePull`

### Investigation

```bash
kubectl describe pod <pod-name> -n hydrus
# Events section will show the exact pull error

# Common causes:
# 1. Wrong image tag
# 2. ACR authentication failure
# 3. Network policy blocking egress to ACR
```

### Fixes

```bash
# Verify image exists in ACR
az acr repository show-tags \
  --name hydrusacr \
  --repository hydrus-backend

# Check that AKS managed identity has AcrPull role
az role assignment list \
  --scope $(az acr show --name hydrusacr --query id -o tsv) \
  --query "[?roleDefinitionName=='AcrPull']"

# If missing, grant the role
az role assignment create \
  --role AcrPull \
  --assignee <AKS_KUBELET_CLIENT_ID> \
  --scope $(az acr show --name hydrusacr --query id -o tsv)
```

---

## Section 5 — Ingress Not Accessible Externally

### Symptoms
- `kubectl get ingress -n hydrus` shows no ADDRESS or IP is `<pending>`
- curl to the public URL times out

### Investigation

```bash
# Check Ingress controller is running
kubectl get pods -n ingress-nginx

# Check Service has an external IP
kubectl get svc -n ingress-nginx ingress-nginx-controller
# If EXTERNAL-IP is <pending>, Azure LoadBalancer is still provisioning (wait 2-3 min)

# Describe Ingress for annotation errors
kubectl describe ingress hydrus-ingress -n hydrus

# Check Ingress class is correct
kubectl get ingressclass
```

### Fixes

- Ensure `ingressClassName: nginx` is set in `ingress.yaml`
- Confirm NGINX Ingress Controller is installed:
  ```bash
  helm install ingress-nginx ingress-nginx/ingress-nginx \
    --namespace ingress-nginx --create-namespace
  ```
- Check Azure subscription quota for Public IP addresses

---

## Section 6 — CI/CD Pipeline Failures

### Stage: SonarQube Scan fails
- Check `SonarQube_Service_Connection` is valid in Azure DevOps → Project Settings → Service Connections
- Verify SonarQube server URL and token in the service connection

### Stage: Trivy scan exits with code 1
- A `CRITICAL` or `HIGH` vulnerability was found in the image
- Run locally to see details: `docker run --rm aquasec/trivy image <image>:<tag>`
- Update the base image or patch the vulnerable package

### Stage: Deploy fails — kubectl not found
- The pipeline pool VM needs kubectl; install with:
  ```yaml
  - task: KubectlInstaller@0
    inputs:
      kubectlVersion: 'latest'
  ```

### Stage: Smoke test returns non-200
- Check pod logs: `kubectl logs -l app=hydrus-backend -n hydrus --since=5m`
- Check Ingress rules: `kubectl describe ingress -n hydrus`
- The pipeline auto-triggers rollback via `kubectl rollout undo`

---

## Section 7 — Terraform Errors

### `Error: Backend configuration changed`
```bash
terraform init -reconfigure
```

### `Error: insufficient permissions`
- Ensure the service principal has `Contributor` on the subscription and `Storage Blob Data Contributor` on the state storage account

### `Error: resource already exists`
- Import the existing resource into state:
  ```bash
  terraform import azurerm_resource_group.main /subscriptions/<SUB>/resourceGroups/hydrus-rg
  ```

### State lock stuck
```bash
az storage blob lease break \
  --container-name tfstate \
  --blob-name hydrus.tfstate \
  --account-name hydrusstatestorage
```

---

## Linux Commands Reference (Inside Pods)

```bash
# Enter a running pod
kubectl exec -it <pod-name> -n hydrus -- bash

# Inside pod: check process list
top
ps aux

# Check open connections
netstat -anp | grep ESTABLISHED | wc -l

# Check memory
cat /proc/meminfo | grep MemAvailable

# Check disk
df -h

# Check DNS resolution
nslookup hydrus-backend-service
```