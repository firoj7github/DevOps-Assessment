# Monitoring & Logging Plan — Hydrus DevOps Assessment

## Overview

This document describes the observability strategy for the Hydrus platform running on AKS. The stack follows the industry-standard **Prometheus → Grafana** pattern for metrics, **Fluent Bit → Log Analytics** for logs, and **Azure Monitor Alerts** for proactive notification.

---

## 1. Metrics — Prometheus & Grafana

### Installation (Kube Prometheus Stack)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update

helm install kube-prometheus-stack \
  prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --create-namespace \
  --set grafana.adminPassword=<SECURE_PASSWORD>
```

This single chart installs:
- **Prometheus** — scrapes metrics from pods, nodes, kube-state-metrics
- **Grafana** — dashboards and alerting UI
- **Alertmanager** — routes alerts to Slack / PagerDuty / email
- **Node Exporter** — host-level CPU, memory, disk metrics
- **kube-state-metrics** — Deployment, Pod, HPA state

### Key Metrics to Collect

#### Cluster Health

| Metric | What it tells you |
|--------|------------------|
| `kube_node_status_condition{condition="Ready"}` | Node availability |
| `kube_pod_status_phase` | Pod phase distribution (Running / Pending / Failed) |
| `kube_deployment_status_replicas_available` | Available vs desired replicas |
| `container_cpu_usage_seconds_total` | CPU usage per container |
| `container_memory_working_set_bytes` | Memory usage per container |

#### Application (Backend API)

| Metric | What it tells you |
|--------|------------------|
| `http_requests_total{status=~"5.."}` | 5xx error rate |
| `http_request_duration_seconds` | Latency histogram (p50, p95, p99) |
| `http_requests_total` | Requests per second (RPS) |
| `asyncpg_pool_size` | DB connection pool utilization |

> FastAPI exposes these via the `prometheus-fastapi-instrumentator` library, mounted at `/metrics`.

#### HPA & Scaling

| Metric | What it tells you |
|--------|------------------|
| `kube_horizontalpodautoscaler_status_current_replicas` | Current pod count |
| `kube_horizontalpodautoscaler_spec_max_replicas` | Headroom before HPA ceiling |

### Grafana Dashboards

| Dashboard | Grafana ID | Purpose |
|-----------|-----------|---------|
| Kubernetes Cluster Overview | 6417 | Node CPU, memory, pod count |
| Kubernetes Deployments | 8588 | Deployment health and replicas |
| FastAPI Observability | 16110 | Request rate, latency, errors |
| PostgreSQL Database | 9628 | Query rate, connections, locks |

Import dashboards via Grafana UI → Dashboards → Import → enter ID.

---

## 2. Logging — Fluent Bit → Azure Log Analytics

### Architecture

```
Pod stdout/stderr
      ↓
Fluent Bit DaemonSet (reads /var/log/containers/*.log)
      ↓
Azure Log Analytics Workspace
      ↓
Azure Monitor / Grafana (Log Analytics data source)
```

### Fluent Bit Installation

```bash
helm repo add fluent https://fluent.github.io/helm-charts

helm install fluent-bit fluent/fluent-bit \
  --namespace logging \
  --create-namespace \
  --set backend.type=azure \
  --set backend.azure.workspace_id=<LOG_ANALYTICS_WORKSPACE_ID> \
  --set backend.azure.workspace_key=<LOG_ANALYTICS_PRIMARY_KEY>
```

### Useful Log Analytics Queries (KQL)

```kusto
// Backend errors in last 1 hour
ContainerLog
| where LogEntry contains "ERROR"
| where ContainerName contains "hydrus-backend"
| where TimeGenerated > ago(1h)
| order by TimeGenerated desc

// 503 errors from Ingress controller
ContainerLog
| where ContainerName contains "ingress-nginx"
| where LogEntry contains "503"
| summarize count() by bin(TimeGenerated, 5m)
| render timechart

// Pod restart events
KubeEvents
| where Reason == "BackOff" or Reason == "OOMKilling"
| where TimeGenerated > ago(6h)
| order by TimeGenerated desc
```

### Application Logging Best Practices

- Use **structured JSON logging** in FastAPI:
  ```python
  import structlog
  log = structlog.get_logger()
  log.info("request_completed", path="/api/v1/tasks", status=200, duration_ms=42)
  ```
- Never log passwords, tokens, or PII
- Use log levels consistently: `DEBUG` (dev only), `INFO` (normal ops), `WARNING` (recoverable), `ERROR` (action needed)

---

## 3. Alerting Rules

### Prometheus Alertmanager Rules

```yaml
# alerts.yaml — apply via kubectl or Helm values
groups:
  - name: hydrus-alerts
    rules:
      - alert: HighErrorRate
        expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.01
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Error rate above 1% for 2 minutes"

      - alert: HighLatencyP99
        expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 0.5
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "P99 latency above 500ms"

      - alert: PodCrashLooping
        expr: rate(kube_pod_container_status_restarts_total[15m]) > 0
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Pod {{ $labels.pod }} is crash-looping"

      - alert: HPAAtMaxReplicas
        expr: kube_horizontalpodautoscaler_status_current_replicas == kube_horizontalpodautoscaler_spec_max_replicas
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "HPA at max replicas — consider raising the ceiling"

      - alert: NodeMemoryPressure
        expr: kube_node_status_condition{condition="MemoryPressure",status="true"} == 1
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Node {{ $labels.node }} under memory pressure"
```

### Alertmanager Routing (Slack + PagerDuty)

```yaml
route:
  group_by: ['alertname', 'namespace']
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
      - api_url: '<SLACK_WEBHOOK_URL>'
        channel: '#hydrus-alerts'
        text: '{{ .CommonAnnotations.summary }}'

  - name: pagerduty-oncall
    pagerduty_configs:
      - routing_key: '<PAGERDUTY_KEY>'
        description: '{{ .CommonAnnotations.summary }}'
```

---

## 4. Azure Monitor Integration

### Container Insights (AKS Native)

Enable from Azure Portal → AKS cluster → Monitoring → Insights, or via CLI:

```bash
az aks enable-addons \
  --resource-group hydrus-rg \
  --name hydrus-aks \
  --addons monitoring \
  --workspace-resource-id /subscriptions/<SUB>/resourceGroups/<RG>/providers/Microsoft.OperationalInsights/workspaces/<WS>
```

This gives out-of-the-box dashboards for:
- Node CPU / memory trends
- Pod-level resource heatmaps
- Container restarts timeline
- Live container logs in Azure Portal

### Azure Monitor Metric Alerts (via Terraform)

```hcl
resource "azurerm_monitor_metric_alert" "aks_cpu" {
  name                = "hydrus-aks-high-cpu"
  resource_group_name = azurerm_resource_group.main.name
  scopes              = [azurerm_kubernetes_cluster.main.id]

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
```

---

## 5. SLA Targets & Key Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| API error rate | > 0.5% | > 1% |
| P99 response time | > 300ms | > 500ms |
| Pod restart rate | > 1/hour | > 5/hour |
| Node CPU utilization | > 70% | > 85% |
| Node memory utilization | > 75% | > 90% |
| HPA replicas at max | — | == max_replicas for 5m |

---

## 6. Runbook Links

| Alert | Runbook |
|-------|---------|
| `HighErrorRate` | See `docs/troubleshooting.md` → Section 3 |
| `PodCrashLooping` | See `docs/troubleshooting.md` → Section 1 |
| `HPAAtMaxReplicas` | Manually scale: `kubectl scale deployment/hydrus-backend --replicas=N` |
| `NodeMemoryPressure` | Add node pool via `az aks nodepool add` or increase VM SKU |