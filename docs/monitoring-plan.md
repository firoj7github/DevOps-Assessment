# Monitoring & Observability Guide — Hydrus

Follow this guide to set up complete production-level monitoring for the Hydrus platform.
Where to look when something goes wrong, what alerts will come,
how to diagnose — everything is here.

---

## Full Monitoring Stack at a Glance

```
AKS Cluster (Hydrus)
        │
        ├── Prometheus ──────────────────── collects metrics
        │       │
        │       └── Alertmanager ────────── sends alerts (Slack / PagerDuty)
        │
        ├── Grafana ─────────────────────── shows dashboards
        │
        ├── Fluent Bit ──────────────────── collects logs
        │       │
        │       └── Log Analytics Workspace ← logs stored in Azure
        │
        └── Azure Monitor ───────────────── Azure-native monitoring
                │
                ├── Container Insights ───── AKS built-in dashboard
                ├── Metric Alerts ────────── alerts when threshold is crossed
                ├── Application Insights ─── traces backend API
                └── Action Groups ────────── who to notify
```

---

## Required Tools

| Tool | Purpose |
|------|-------------|
| Azure CLI | Manage Azure resources |
| kubectl | Send commands to K8s cluster |
| Helm | Install charts |
| Terraform | Create Azure resources as code |

---

## Phase 1 — Azure Monitor Container Insights

**What happens:** AKS cluster's built-in monitoring gets enabled.
Node, Pod, Container — all visible in Azure Portal.
No extra tools need to be installed.

### Step 1 — Create Log Analytics Workspace

**Via Azure Portal:**

1. Go to https://portal.azure.com
2. In the search bar, type: `Log Analytics workspaces`
3. Click **+ Create**
4. Fill in the form:

| Field | Value |
|-------|-------|
| Subscription | Your subscription |
| Resource group | `hydrus-rg` |
| Name | `hydrus-logs` |
| Region | Same region as your AKS |

5. Click **Review + create** → **Create**
6. When deployed, click **Go to resource**
7. From the left menu go to **Agents** → **Log Analytics agent instructions**
8. Note the **Workspace ID** and **Primary key** — you'll need them later

---

### Step 2 — Enable Container Insights

**Via Azure Portal:**

1. In the Portal, search: `Kubernetes services`
2. Click on `hydrus-aks`
3. In the left menu under **Monitoring** section, click **Insights**
4. A **Configure monitoring** button will appear — click it
5. From the **Log Analytics workspace** dropdown, select `hydrus-logs`
6. Click **Configure**

Takes 5-10 minutes to start up.

**Can also be done via CLI:**

```bash
# Get Workspace ID
WS_ID=$(az monitor log-analytics workspace show \
  --resource-group hydrus-rg \
  --workspace-name hydrus-logs \
  --query id --output tsv)

# Enable Container Insights
az aks enable-addons \
  --resource-group hydrus-rg \
  --name hydrus-aks \
  --addons monitoring \
  --workspace-resource-id $WS_ID
```

---

### Step 3 — View Container Insights

In the Portal, go to AKS → **Insights** to see all of this:

| Tab | What it shows |
|-----|----------|
| Cluster | Node CPU, Memory overall |
| Nodes | Resource usage per Node |
| Controllers | Deployment, StatefulSet health |
| Containers | CPU, Memory, restart count per Container |
| Live Logs | Real-time container log |

---

## Phase 2 — Application Insights (Backend API Tracing)

**What happens:** Every request to the backend API can be traced.
Which endpoint is slow, where errors occur — all visible in detail.

### Step 1 — Create Application Insights

**Via Azure Portal:**

1. In the search bar, type: `Application Insights`
2. Click **+ Create**
3. Fill in the form:

| Field | Value |
|-------|-------|
| Subscription | Your subscription |
| Resource group | `hydrus-rg` |
| Name | `hydrus-appinsights` |
| Region | Same region as your AKS |
| Resource Mode | Workspace-based |
| Log Analytics Workspace | `hydrus-logs` |

4. Click **Review + create** → **Create**
5. When deployed, click **Go to resource**
6. On the **Overview** page, note the **Instrumentation Key** and **Connection String**

---

### Step 2 — Add Connection String to K8s ConfigMap

```bash
# Update ConfigMap
kubectl patch configmap hydrus-config \
  --namespace hydrus \
  --patch '{"data":{"APPLICATIONINSIGHTS_CONNECTION_STRING":"InstrumentationKey=xxxx;IngestionEndpoint=..."}}'
```

---

### Step 3 — Add SDK to Backend API

In `backend/requirements.txt`, add:

```
opencensus-ext-azure==1.1.9
opencensus-ext-fastapi==0.7.3
```

In `backend/main.py`, add:

```python
import os
from opencensus.ext.azure.trace_exporter import AzureExporter
from opencensus.ext.fastapi.fastapi_middleware import FastAPIMiddleware
from opencensus.trace.samplers import ProbabilitySampler

app.add_middleware(
    FastAPIMiddleware,
    exporter=AzureExporter(
        connection_string=os.environ["APPLICATIONINSIGHTS_CONNECTION_STRING"]
    ),
    sampler=ProbabilitySampler(rate=1.0),  # 100% request trace
)
```

---

### Step 4 — What You Can See in Application Insights

In the Portal, Application Insights → left menu:

| Section | What it shows |
|---------|----------|
| **Overview** | Request rate, failure rate, response time — live |
| **Live Metrics** | Current requests, failures, CPU — real-time |
| **Failures** | Which endpoint has errors, with stack trace |
| **Performance** | Which endpoint is slowest, dependency breakdown |
| **Transaction search** | Full journey of a specific request |
| **Application map** | Visual map of Backend → Database connection |

---

## Phase 3 — Prometheus & Grafana

**What happens:** Kubernetes-level metrics are collected.
Custom dashboards can be built.
Alerting rules can be written.

### Step 1 — Install via Helm

```bash
# Add Prometheus community chart
helm repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts
helm repo update

# Install kube-prometheus-stack
# This installs Prometheus + Grafana + Alertmanager all at once
helm install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --set grafana.adminPassword=your_grafana_password \
  --set grafana.service.type=LoadBalancer
```

Verify install:

```bash
kubectl get pods -n monitoring
```

Ready when all pods show STATUS `Running`.

---

### Step 2 — Log in to Grafana

```bash
# Get Grafana's Public IP
kubectl get svc -n monitoring kube-prometheus-stack-grafana
```

An IP will appear in the `EXTERNAL-IP` column.
Go in browser: `http://<EXTERNAL-IP>`

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | Whatever you entered during install |

---

### Step 3 — Import Ready-made Dashboards

In Grafana → left menu → **Dashboards** → **Import**

Import each of the following IDs one by one:

| Dashboard | ID | What it shows |
|-----------|-----|----------|
| Kubernetes Cluster Overview | `6417` | Node CPU, Memory, Pod count |
| Kubernetes Deployments | `8588` | Deployment health, replica status |
| FastAPI Observability | `16110` | Request rate, latency, error rate |
| PostgreSQL Database | `9628` | Query rate, connection, lock |

**How to import:**
1. On the **Import** page, enter the ID
2. Click **Load**
3. Select **Prometheus** datasource
4. Click **Import**

---

### Step 4 — Apply Alerting Rules

Save the file below as `k8s/alerts.yaml`:

```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: hydrus-alerts
  namespace: monitoring
  labels:
    release: kube-prometheus-stack
spec:
  groups:
    - name: hydrus-api
      rules:

        # Alert if more than 1% of requests fail
        - alert: HighErrorRate
          expr: |
            rate(http_requests_total{status=~"5.."}[5m])
            /
            rate(http_requests_total[5m]) > 0.01
          for: 2m
          labels:
            severity: critical
          annotations:
            summary: "Error rate {{ $value | humanizePercentage }} — above 1%"
            description: "Backend API has been failing more than 1% of requests for 2 minutes."

        # Alert if P99 latency exceeds 500ms
        - alert: HighLatencyP99
          expr: |
            histogram_quantile(0.99,
              rate(http_request_duration_seconds_bucket[5m])
            ) > 0.5
          for: 3m
          labels:
            severity: warning
          annotations:
            summary: "P99 latency {{ $value | humanizeDuration }} — above 500ms"
            description: "99% of requests have response time above 500ms."

        # Alert if pod keeps restarting
        - alert: PodCrashLooping
          expr: |
            rate(kube_pod_container_status_restarts_total{
              namespace="hydrus"
            }[15m]) * 60 > 1
          for: 5m
          labels:
            severity: critical
          annotations:
            summary: "Pod {{ $labels.pod }} crash-looping"
            description: "Pod is restarting more than once per minute."

        # Alert if HPA reaches max replicas
        - alert: HPAAtMaxReplicas
          expr: |
            kube_horizontalpodautoscaler_status_current_replicas
            ==
            kube_horizontalpodautoscaler_spec_max_replicas
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "HPA {{ $labels.horizontalpodautoscaler }} at max replicas"
            description: "HPA is at maximum limit — will not scale further if load increases."

    - name: hydrus-infrastructure
      rules:

        # Critical alert if node goes into memory pressure
        - alert: NodeMemoryPressure
          expr: |
            kube_node_status_condition{
              condition="MemoryPressure",
              status="true"
            } == 1
          for: 1m
          labels:
            severity: critical
          annotations:
            summary: "Node {{ $labels.node }} memory pressure"
            description: "Node is low on memory — pods may be evicted."

        # Alert if node CPU exceeds 85%
        - alert: NodeHighCPU
          expr: |
            100 - (avg by(node) (
              rate(node_cpu_seconds_total{mode="idle"}[5m])
            ) * 100) > 85
          for: 5m
          labels:
            severity: warning
          annotations:
            summary: "Node {{ $labels.node }} CPU {{ $value | humanize }}%"
            description: "Node CPU usage has exceeded 85%."

        # Alert if Postgres connection pool is nearly full
        - alert: PostgresConnectionPoolHigh
          expr: asyncpg_pool_size > 80
          for: 2m
          labels:
            severity: warning
          annotations:
            summary: "Postgres connection pool {{ $value }}% full"
            description: "Database connections may run out."
```

Apply:

```bash
kubectl apply -f k8s/alerts.yaml
```

---

### Step 5 — Send Notifications to Slack via Alertmanager

**First create a Slack Webhook URL:**

1. Go to https://api.slack.com/apps
2. **Create New App** → **From scratch**
3. App name: `Hydrus Alerts`, select your workspace
4. In the left menu **Incoming Webhooks** → **Activate Incoming Webhooks** turn ON
5. **Add New Webhook to Workspace** → select channel (`#hydrus-alerts`)
6. Copy the **Webhook URL**:
   ```
   https://hooks.slack.com/services/xxx/yyy/zzz
   ```

**Apply Alertmanager config:**

```bash
kubectl create secret generic alertmanager-config \
  --namespace monitoring \
  --from-literal=alertmanager.yaml='
route:
  group_by: ["alertname", "namespace"]
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: slack-general
  routes:
    - match:
        severity: critical
      receiver: pagerduty-oncall

receivers:
  - name: slack-general
    slack_configs:
      - api_url: "https://hooks.slack.com/services/xxx/yyy/zzz"
        channel: "#hydrus-alerts"
        title: "{{ .CommonLabels.alertname }}"
        text: "{{ .CommonAnnotations.description }}"
        color: |
          {{ if eq .CommonLabels.severity "critical" }}danger{{ else }}warning{{ end }}

  - name: pagerduty-oncall
    pagerduty_configs:
      - routing_key: "<PAGERDUTY_ROUTING_KEY>"
        description: "{{ .CommonAnnotations.summary }}"
' \
  --dry-run=client -o yaml | kubectl apply -f -
```

---

## Phase 4 — View Logs with Log Analytics

**What happens:** Logs from all pods are stored in Azure Log Analytics.
You can search logs from any time using KQL queries.

### Step 1 — Install Fluent Bit

Fluent Bit collects logs from all pods and sends them to Log Analytics.

```bash
# Get Workspace ID and Key
WS_ID=$(az monitor log-analytics workspace show \
  --resource-group hydrus-rg \
  --workspace-name hydrus-logs \
  --query customerId --output tsv)

WS_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group hydrus-rg \
  --workspace-name hydrus-logs \
  --query primarySharedKey --output tsv)

# Install Fluent Bit
helm repo add fluent https://fluent.github.io/helm-charts
helm repo update

helm install fluent-bit fluent/fluent-bit \
  --namespace logging \
  --create-namespace \
  --set backend.type=azure \
  --set backend.azure.workspace_id=$WS_ID \
  --set backend.azure.workspace_key=$WS_KEY
```

---

### Step 2 — Query in Log Analytics

In the Portal → search `Log Analytics workspaces` → `hydrus-logs` → **Logs**

Copy the KQL queries below and click **Run**:

**View all ERROR logs from backend:**

```kusto
ContainerLog
| where ContainerName contains "hydrus-backend"
| where LogEntry contains "ERROR"
| where TimeGenerated > ago(1h)
| project TimeGenerated, LogEntry
| order by TimeGenerated desc
```

---

**How many errors per 5 minutes:**

```kusto
ContainerLog
| where ContainerName contains "hydrus-backend"
| where LogEntry contains "ERROR"
| summarize ErrorCount=count() by bin(TimeGenerated, 5m)
| render timechart
```

---

**View 5xx errors from Ingress:**

```kusto
ContainerLog
| where ContainerName contains "ingress-nginx"
| where LogEntry matches regex "\" 5[0-9]{2} "
| summarize count() by bin(TimeGenerated, 5m)
| render timechart
```

---

**View Pod restart or OOMKill events:**

```kusto
KubeEvents
| where Reason in ("BackOff", "OOMKilling", "Evicted")
| where TimeGenerated > ago(6h)
| project TimeGenerated, Reason, Message, Name
| order by TimeGenerated desc
```

---

**View slow requests (more than 1 second):**

```kusto
ContainerLog
| where ContainerName contains "hydrus-backend"
| where LogEntry contains "duration"
| extend duration = todouble(extract('"duration_ms":([0-9.]+)', 1, LogEntry))
| where duration > 1000
| project TimeGenerated, duration, LogEntry
| order by duration desc
```

---

## Phase 5 — Azure Monitor Metric Alerts

**What happens:** Azure watches metrics on its own. Sends email or SMS when threshold is crossed.
Basic alerting works without Prometheus.

### Step 1 — Create Action Group

Action Group means — who to notify when an alert comes.

**Via Azure Portal:**

1. Search: `Monitor`
2. In the left menu → **Alerts** → **Action groups** → **+ Create**
3. Fill in the form:

| Field | Value |
|-------|-------|
| Subscription | Your subscription |
| Resource group | `hydrus-rg` |
| Action group name | `hydrus-oncall` |
| Display name | `Hydrus OnCall` |

4. Go to **Notifications** tab:

| Notification type | Name | Value |
|------------------|------|-------|
| Email/SMS/Push/Voice | `email-alert` | Enter your email address |

5. **Review + create** → **Create**

---

### Step 2 — Create Metric Alert

**AKS Node CPU Alert:**

1. In Portal → `Monitor` → **Alerts** → **+ Create** → **Alert rule**
2. In **Select a resource**, select `hydrus-aks`
3. **Condition** tab → **Add condition**:

| Field | Value |
|-------|-------|
| Signal name | `CPU Usage Percentage` |
| Aggregation | Average |
| Operator | Greater than |
| Threshold | `80` |
| Evaluation frequency | 5 minutes |
| Lookback period | 15 minutes |

4. **Actions** tab → **+ Select action groups** → select `hydrus-oncall`
5. **Details** tab:

| Field | Value |
|-------|-------|
| Alert rule name | `hydrus-aks-high-cpu` |
| Severity | 2 — Warning |

6. **Review + create** → **Create**

---

**Using the same method, create these alerts too:**

| Alert Name | Metric | Threshold | Severity |
|-----------|--------|-----------|----------|
| `hydrus-aks-high-memory` | Memory Working Set Percentage | > 85% | 2 — Warning |
| `hydrus-aks-pod-failed` | Pod Count (phase=Failed) | > 0 | 1 — Error |
| `hydrus-aks-node-not-ready` | Node Status (NotReady) | > 0 | 0 — Critical |

---

### Step 3 — Create Alerts with Terraform (if you want to keep them as code)

In `terraform/monitoring.tf`:

```hcl
# Action Group — who to notify
resource "azurerm_monitor_action_group" "oncall" {
  name                = "hydrus-oncall"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "oncall"

  email_receiver {
    name          = "email-alert"
    email_address = "your-email@example.com"
  }
}

# AKS Node CPU Alert
resource "azurerm_monitor_metric_alert" "aks_cpu" {
  name                = "hydrus-aks-high-cpu"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_kubernetes_cluster.main.id]
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "Microsoft.ContainerService/managedClusters"
    metric_name      = "node_cpu_usage_percentage"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 80
  }

  action {
    action_group_id = azurerm_monitor_action_group.oncall.id
  }
}

# AKS Node Memory Alert
resource "azurerm_monitor_metric_alert" "aks_memory" {
  name                = "hydrus-aks-high-memory"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_kubernetes_cluster.main.id]
  severity            = 2
  frequency           = "PT5M"
  window_size         = "PT15M"

  criteria {
    metric_namespace = "Microsoft.ContainerService/managedClusters"
    metric_name      = "node_memory_working_set_percentage"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 85
  }

  action {
    action_group_id = azurerm_monitor_action_group.oncall.id
  }
}

# Pod Failed Alert
resource "azurerm_monitor_metric_alert" "pod_failed" {
  name                = "hydrus-aks-pod-failed"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_kubernetes_cluster.main.id]
  severity            = 1
  frequency           = "PT1M"
  window_size         = "PT5M"

  criteria {
    metric_namespace = "Microsoft.ContainerService/managedClusters"
    metric_name      = "kube_pod_status_phase"
    aggregation      = "Average"
    operator         = "GreaterThan"
    threshold        = 0

    dimension {
      name     = "phase"
      operator = "Include"
      values   = ["Failed"]
    }
  }

  action {
    action_group_id = azurerm_monitor_action_group.oncall.id
  }
}
```

Apply:

```bash
cd terraform
terraform plan -var-file=environments/prod.tfvars
terraform apply
```

---

## Phase 6 — Workbook (Production Dashboard)

**What happens:** With Azure Monitor Workbook, all metrics can be seen in one place.
A nice dashboard can be built in Azure Portal even without Grafana.

### Step 1 — Create Workbook

1. In Portal → `Monitor` → **Workbooks** in the left menu → **+ New**
2. Click **+ Add** → **Add query**
3. Enter the query below:

```kusto
// Pod restart timeline
KubePodInventory
| where Namespace == "hydrus"
| summarize RestartCount=sum(PodRestartCount) by bin(TimeGenerated, 5m), Name
| render timechart
```

4. **+ Add** → **Add metric** → select AKS cluster → add CPU metric
5. **Save** → name it: `Hydrus Production Dashboard`

---

## SLA Targets and Alert Thresholds

| Metric | Normal | Warning | Critical |
|--------|--------|---------|----------|
| API error rate | < 0.1% | > 0.5% | > 1% |
| P99 response time | < 200ms | > 300ms | > 500ms |
| Pod restart (per hour) | 0 | > 1 | > 5 |
| Node CPU | < 60% | > 70% | > 85% |
| Node Memory | < 65% | > 75% | > 90% |
| HPA replicas at max | — | 3 min | 5 min |
| DB connection pool | < 50% | > 70% | > 85% |

---

## Troubleshooting — Runbook

### Pod CrashLoopBackOff

```bash
# See which pod is crashing
kubectl get pods -n hydrus

# View that pod's logs
kubectl logs -n hydrus <pod-name> --previous

# View pod events
kubectl describe pod -n hydrus <pod-name>
```

---

### High Memory — OOMKilled

```bash
# View memory usage
kubectl top pods -n hydrus

# Increase resource limit (temporary fix)
kubectl set resources deployment/hydrus-backend \
  --namespace hydrus \
  --limits=memory=1Gi
```

---

### HPA Stuck at Max Replicas

```bash
# View HPA status
kubectl get hpa -n hydrus

# Manual scale (temporary)
kubectl scale deployment/hydrus-backend \
  --namespace hydrus \
  --replicas=15

# Or increase HPA maxReplicas
kubectl patch hpa hydrus-backend-hpa \
  --namespace hydrus \
  --patch '{"spec":{"maxReplicas":20}}'
```

---

### Database Connections Running Out

```bash
# Connect to Postgres pod
kubectl exec -it -n hydrus statefulset/hydrus-postgres \
  -- psql -U hydrus -d hydrusdb

# View active connections
SELECT count(*), state
FROM pg_stat_activity
GROUP BY state;

# Kill idle connections
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
AND query_start < now() - interval '10 minutes';
```

---

### Ingress 502/503 Error

```bash
# View ingress controller logs
kubectl logs -n ingress-nginx \
  deployment/ingress-nginx-controller \
  --tail=100

# Check if backend service is reachable
kubectl get endpoints -n hydrus hydrus-backend-svc
```