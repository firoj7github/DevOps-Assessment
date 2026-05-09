# Monitoring & Observability Guide — Hydrus

এই guide follow করলে Hydrus platform এর সম্পূর্ণ production-level monitoring
setup করা যাবে। কোনো সমস্যা হলে কোথায় দেখতে হবে, কী alert আসবে,
কীভাবে diagnose করতে হবে — সব এখানে আছে।

---

## এক নজরে পুরো Monitoring Stack

```
AKS Cluster (Hydrus)
        │
        ├── Prometheus ──────────────────── metrics collect করে
        │       │
        │       └── Alertmanager ────────── alert পাঠায় (Slack / PagerDuty)
        │
        ├── Grafana ─────────────────────── dashboard এ দেখায়
        │
        ├── Fluent Bit ──────────────────── log collect করে
        │       │
        │       └── Log Analytics Workspace ← Azure এ log store হয়
        │
        └── Azure Monitor ───────────────── Azure-native monitoring
                │
                ├── Container Insights ───── AKS built-in dashboard
                ├── Metric Alerts ────────── threshold পার হলে alert
                ├── Application Insights ─── backend API trace করে
                └── Action Groups ────────── কাকে notify করবে
```

---

## প্রয়োজনীয় tools

| Tool | কী কাজে লাগে |
|------|-------------|
| Azure CLI | Azure resource manage করতে |
| kubectl | K8s cluster এ command দিতে |
| Helm | Chart install করতে |
| Terraform | Azure resource কোড দিয়ে তৈরি করতে |

---

## Phase 1 — Azure Monitor Container Insights

**কী হয়:** AKS cluster এর built-in monitoring চালু হয়।
Node, Pod, Container সব Azure Portal এ দেখা যায়।
কোনো extra tool install লাগে না।

### ধাপ ১ — Log Analytics Workspace তৈরি করো

**Azure Portal দিয়ে:**

1. https://portal.azure.com এ যাও
2. Search bar এ লেখো: `Log Analytics workspaces`
3. **+ Create** click করো
4. Form fill করো:

| Field | Value |
|-------|-------|
| Subscription | তোমার subscription |
| Resource group | `hydrus-rg` |
| Name | `hydrus-logs` |
| Region | তোমার AKS এর একই region |

5. **Review + create** → **Create** click করো
6. Deploy হলে **Go to resource** click করো
7. বাম menu থেকে **Agents** → **Log Analytics agent instructions** এ যাও
8. **Workspace ID** আর **Primary key** নোট করো — পরে লাগবে

---

### ধাপ ২ — Container Insights Enable করো

**Azure Portal দিয়ে:**

1. Portal এ search করো: `Kubernetes services`
2. `hydrus-aks` এ click করো
3. বাম menu তে **Monitoring** section এ **Insights** click করো
4. **Configure monitoring** button দেখাবে — click করো
5. **Log Analytics workspace** dropdown থেকে `hydrus-logs` select করো
6. **Configure** click করো

চালু হতে ৫-১০ মিনিট লাগে।

**CLI দিয়েও করা যায়:**

```bash
# Workspace ID বের করো
WS_ID=$(az monitor log-analytics workspace show \
  --resource-group hydrus-rg \
  --workspace-name hydrus-logs \
  --query id --output tsv)

# Container Insights enable করো
az aks enable-addons \
  --resource-group hydrus-rg \
  --name hydrus-aks \
  --addons monitoring \
  --workspace-resource-id $WS_ID
```

---

### ধাপ ৩ — Container Insights দেখো

Portal এ AKS → **Insights** এ গেলে এই সব দেখা যাবে:

| Tab | কী দেখায় |
|-----|----------|
| Cluster | Node CPU, Memory overall |
| Nodes | প্রতিটা Node এর resource usage |
| Controllers | Deployment, StatefulSet health |
| Containers | প্রতিটা Container এর CPU, Memory, restart count |
| Live Logs | Real-time container log |

---

## Phase 2 — Application Insights (Backend API Tracing)

**কী হয়:** Backend API এর প্রতিটা request trace করা যায়।
কোন endpoint slow, কোথায় error — সব detail দেখা যায়।

### ধাপ ১ — Application Insights তৈরি করো

**Azure Portal দিয়ে:**

1. Search bar এ লেখো: `Application Insights`
2. **+ Create** click করো
3. Form fill করো:

| Field | Value |
|-------|-------|
| Subscription | তোমার subscription |
| Resource group | `hydrus-rg` |
| Name | `hydrus-appinsights` |
| Region | তোমার AKS এর একই region |
| Resource Mode | Workspace-based |
| Log Analytics Workspace | `hydrus-logs` |

4. **Review + create** → **Create** click করো
5. Deploy হলে **Go to resource** click করো
6. **Overview** page এ **Instrumentation Key** আর **Connection String** নোট করো

---

### ধাপ ২ — Connection String K8s ConfigMap এ দাও

```bash
# ConfigMap update করো
kubectl patch configmap hydrus-config \
  --namespace hydrus \
  --patch '{"data":{"APPLICATIONINSIGHTS_CONNECTION_STRING":"InstrumentationKey=xxxx;IngestionEndpoint=..."}}'
```

---

### ধাপ ৩ — Backend API তে SDK যোগ করো

`backend/requirements.txt` এ যোগ করো:

```
opencensus-ext-azure==1.1.9
opencensus-ext-fastapi==0.7.3
```

`backend/main.py` এ যোগ করো:

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

### ধাপ ৪ — Application Insights এ কী দেখা যাবে

Portal এ Application Insights → বাম menu:

| Section | কী দেখায় |
|---------|----------|
| **Overview** | Request rate, failure rate, response time — live |
| **Live Metrics** | এই মুহূর্তের request, failure, CPU — real-time |
| **Failures** | কোন endpoint এ error, stack trace সহ |
| **Performance** | কোন endpoint সবচেয়ে slow, dependency breakdown |
| **Transaction search** | একটা specific request এর পুরো journey |
| **Application map** | Backend → Database connection visual map |

---

## Phase 3 — Prometheus & Grafana

**কী হয়:** Kubernetes-level metrics collect হয়।
Custom dashboard বানানো যায়।
Alerting rule লেখা যায়।

### ধাপ ১ — Helm দিয়ে Install করো

```bash
# Prometheus community chart যোগ করো
helm repo add prometheus-community \
  https://prometheus-community.github.io/helm-charts
helm repo update

# kube-prometheus-stack install করো
# এটা একসাথে Prometheus + Grafana + Alertmanager install করে
helm install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --set grafana.adminPassword=তোমার_grafana_password \
  --set grafana.service.type=LoadBalancer
```

Install যাচাই করো:

```bash
kubectl get pods -n monitoring
```

সব pod এর STATUS `Running` দেখালে ready।

---

### ধাপ ২ — Grafana এ Login করো

```bash
# Grafana এর Public IP বের করো
kubectl get svc -n monitoring kube-prometheus-stack-grafana
```

`EXTERNAL-IP` কলামে IP দেখাবে।
Browser এ যাও: `http://<EXTERNAL-IP>`

| Field | Value |
|-------|-------|
| Username | `admin` |
| Password | install এ যা দিয়েছিলে |

---

### ধাপ ৩ — Ready-made Dashboard Import করো

Grafana এ → বাম menu → **Dashboards** → **Import**

নিচের ID গুলো একে একে import করো:

| Dashboard | ID | কী দেখায় |
|-----------|-----|----------|
| Kubernetes Cluster Overview | `6417` | Node CPU, Memory, Pod count |
| Kubernetes Deployments | `8588` | Deployment health, replica status |
| FastAPI Observability | `16110` | Request rate, latency, error rate |
| PostgreSQL Database | `9628` | Query rate, connection, lock |

**Import করার নিয়ম:**
1. **Import** page এ ID লেখো
2. **Load** click করো
3. **Prometheus** datasource select করো
4. **Import** click করো

---

### ধাপ ৪ — Alerting Rules Apply করো

নিচের file টা `k8s/alerts.yaml` নামে save করো:

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

        # ১% এর বেশি request fail করলে alert
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
            description: "Backend API এ 2 মিনিট ধরে 1% এর বেশি request fail করছে।"

        # P99 latency 500ms এর বেশি হলে alert
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
            description: "99% request এর response time 500ms ছাড়িয়ে গেছে।"

        # Pod বারবার restart করলে alert
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
            description: "Pod প্রতি মিনিটে একবারের বেশি restart করছে।"

        # HPA সর্বোচ্চ সীমায় পৌঁছে গেলে alert
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
            description: "HPA সর্বোচ্চ সীমায় আছে — load বেশি হলে আর scale হবে না।"

    - name: hydrus-infrastructure
      rules:

        # Node memory pressure এ গেলে critical alert
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
            description: "Node এ memory কম — pod evict হতে পারে।"

        # Node CPU 85% এর বেশি হলে alert
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
            description: "Node CPU usage 85% ছাড়িয়ে গেছে।"

        # Postgres connection pool ভরে গেলে alert
        - alert: PostgresConnectionPoolHigh
          expr: asyncpg_pool_size > 80
          for: 2m
          labels:
            severity: warning
          annotations:
            summary: "Postgres connection pool {{ $value }}% full"
            description: "Database connection শেষ হয়ে যেতে পারে।"
```

Apply করো:

```bash
kubectl apply -f k8s/alerts.yaml
```

---

### ধাপ ৫ — Alertmanager দিয়ে Slack এ Notification পাঠাও

**প্রথমে Slack Webhook URL তৈরি করো:**

1. https://api.slack.com/apps এ যাও
2. **Create New App** → **From scratch**
3. App নাম: `Hydrus Alerts`, workspace select করো
4. বাম menu তে **Incoming Webhooks** → **Activate Incoming Webhooks** ON করো
5. **Add New Webhook to Workspace** → channel select করো (`#hydrus-alerts`)
6. **Webhook URL** copy করো:
   ```
   https://hooks.slack.com/services/xxx/yyy/zzz
   ```

**Alertmanager config apply করো:**

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

## Phase 4 — Log Analytics দিয়ে Log দেখো

**কী হয়:** সব pod এর log Azure Log Analytics এ জমা হয়।
KQL query দিয়ে যেকোনো সময়ের log খোঁজা যায়।

### ধাপ ১ — Fluent Bit Install করো

Fluent Bit সব pod এর log collect করে Log Analytics এ পাঠায়।

```bash
# Workspace ID আর Key বের করো
WS_ID=$(az monitor log-analytics workspace show \
  --resource-group hydrus-rg \
  --workspace-name hydrus-logs \
  --query customerId --output tsv)

WS_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group hydrus-rg \
  --workspace-name hydrus-logs \
  --query primarySharedKey --output tsv)

# Fluent Bit install করো
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

### ধাপ ২ — Log Analytics এ Query করো

Portal এ → search করো `Log Analytics workspaces` → `hydrus-logs` → **Logs**

নিচের KQL query গুলো copy করে **Run** করো:

**Backend এর সব ERROR log দেখো:**

```kusto
ContainerLog
| where ContainerName contains "hydrus-backend"
| where LogEntry contains "ERROR"
| where TimeGenerated > ago(1h)
| project TimeGenerated, LogEntry
| order by TimeGenerated desc
```

---

**প্রতি ৫ মিনিটে কতটা error হচ্ছে:**

```kusto
ContainerLog
| where ContainerName contains "hydrus-backend"
| where LogEntry contains "ERROR"
| summarize ErrorCount=count() by bin(TimeGenerated, 5m)
| render timechart
```

---

**Ingress এর 5xx error দেখো:**

```kusto
ContainerLog
| where ContainerName contains "ingress-nginx"
| where LogEntry matches regex "\" 5[0-9]{2} "
| summarize count() by bin(TimeGenerated, 5m)
| render timechart
```

---

**Pod restart বা OOMKill event দেখো:**

```kusto
KubeEvents
| where Reason in ("BackOff", "OOMKilling", "Evicted")
| where TimeGenerated > ago(6h)
| project TimeGenerated, Reason, Message, Name
| order by TimeGenerated desc
```

---

**Slow request দেখো (1 second এর বেশি):**

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

**কী হয়:** Azure নিজেই metric দেখে। Threshold পার হলে email বা SMS পাঠায়।
Prometheus ছাড়াই basic alerting কাজ করে।

### ধাপ ১ — Action Group তৈরি করো

Action Group মানে — alert আসলে কাকে notify করবে।

**Azure Portal দিয়ে:**

1. Search করো: `Monitor`
2. বাম menu তে **Alerts** → **Action groups** → **+ Create**
3. Form fill করো:

| Field | Value |
|-------|-------|
| Subscription | তোমার subscription |
| Resource group | `hydrus-rg` |
| Action group name | `hydrus-oncall` |
| Display name | `Hydrus OnCall` |

4. **Notifications** tab এ যাও:

| Notification type | Name | Value |
|------------------|------|-------|
| Email/SMS/Push/Voice | `email-alert` | তোমার email address দাও |

5. **Review + create** → **Create**

---

### ধাপ ২ — Metric Alert তৈরি করো

**AKS Node CPU Alert:**

1. Portal এ → `Monitor` → **Alerts** → **+ Create** → **Alert rule**
2. **Select a resource** এ `hydrus-aks` select করো
3. **Condition** tab → **Add condition**:

| Field | Value |
|-------|-------|
| Signal name | `CPU Usage Percentage` |
| Aggregation | Average |
| Operator | Greater than |
| Threshold | `80` |
| Evaluation frequency | 5 minutes |
| Lookback period | 15 minutes |

4. **Actions** tab → **+ Select action groups** → `hydrus-oncall` select করো
5. **Details** tab:

| Field | Value |
|-------|-------|
| Alert rule name | `hydrus-aks-high-cpu` |
| Severity | 2 — Warning |

6. **Review + create** → **Create**

---

**একই পদ্ধতিতে এই alert গুলোও বানাও:**

| Alert নাম | Metric | Threshold | Severity |
|-----------|--------|-----------|----------|
| `hydrus-aks-high-memory` | Memory Working Set Percentage | > 85% | 2 — Warning |
| `hydrus-aks-pod-failed` | Pod Count (phase=Failed) | > 0 | 1 — Error |
| `hydrus-aks-node-not-ready` | Node Status (NotReady) | > 0 | 0 — Critical |

---

### ধাপ ৩ — Terraform দিয়ে Alert বানাও (Code হিসেবে রাখতে চাইলে)

`terraform/monitoring.tf` ফাইলে:

```hcl
# Action Group — কাকে notify করবে
resource "azurerm_monitor_action_group" "oncall" {
  name                = "hydrus-oncall"
  resource_group_name = azurerm_resource_group.main.name
  short_name          = "oncall"

  email_receiver {
    name          = "email-alert"
    email_address = "তোমার-email@example.com"
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

Apply করো:

```bash
cd terraform
terraform plan -var-file=environments/prod.tfvars
terraform apply
```

---

## Phase 6 — Workbook (Production Dashboard)

**কী হয়:** Azure Monitor Workbook দিয়ে একটাই জায়গায় সব metric দেখা যায়।
Grafana ছাড়াও Azure Portal এ সুন্দর dashboard বানানো যায়।

### ধাপ ১ — Workbook তৈরি করো

1. Portal এ → `Monitor` → বাম menu তে **Workbooks** → **+ New**
2. **+ Add** → **Add query** click করো
3. নিচের query দাও:

```kusto
// Pod restart timeline
KubePodInventory
| where Namespace == "hydrus"
| summarize RestartCount=sum(PodRestartCount) by bin(TimeGenerated, 5m), Name
| render timechart
```

4. **+ Add** → **Add metric** → AKS cluster select করো → CPU metric যোগ করো
5. **Save** → নাম দাও: `Hydrus Production Dashboard`

---

## SLA Target ও Alert Threshold

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

## সমস্যা হলে কী করবে — Runbook

### Pod CrashLoopBackOff

```bash
# কোন pod crash করছে দেখো
kubectl get pods -n hydrus

# সেই pod এর log দেখো
kubectl logs -n hydrus <pod-name> --previous

# Pod এর event দেখো
kubectl describe pod -n hydrus <pod-name>
```

---

### High Memory — OOMKilled

```bash
# Memory usage দেখো
kubectl top pods -n hydrus

# Resource limit বাড়াও (temporary fix)
kubectl set resources deployment/hydrus-backend \
  --namespace hydrus \
  --limits=memory=1Gi
```

---

### HPA Max Replicas এ আটকে গেছে

```bash
# HPA status দেখো
kubectl get hpa -n hydrus

# Manual scale করো (temporary)
kubectl scale deployment/hydrus-backend \
  --namespace hydrus \
  --replicas=15

# অথবা HPA এর maxReplicas বাড়াও
kubectl patch hpa hydrus-backend-hpa \
  --namespace hydrus \
  --patch '{"spec":{"maxReplicas":20}}'
```

---

### Database Connection শেষ হয়ে যাচ্ছে

```bash
# Postgres pod এ connect করো
kubectl exec -it -n hydrus statefulset/hydrus-postgres \
  -- psql -U hydrus -d hydrusdb

# Active connection দেখো
SELECT count(*), state
FROM pg_stat_activity
GROUP BY state;

# Idle connection kill করো
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE state = 'idle'
AND query_start < now() - interval '10 minutes';
```

---

### Ingress 502/503 error

```bash
# Ingress controller log দেখো
kubectl logs -n ingress-nginx \
  deployment/ingress-nginx-controller \
  --tail=100

# Backend service এ পৌঁছানো যাচ্ছে কিনা দেখো
kubectl get endpoints -n hydrus hydrus-backend-svc
```