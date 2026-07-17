# Grafana Skill

## Purpose
Metrics visualization, dashboards, and alerting for all applications and infrastructure. Central monitoring hub.

## When to Activate
- Setting up monitoring for any application
- Creating or editing dashboards
- Configuring alerts and notifications
- Adding data sources (Prometheus, CloudWatch, Elasticsearch)
- Debugging performance issues using metrics

## Sub-Skills
| File | When to Read |
|------|-------------|
| `dashboards.md` | Creating or editing Grafana dashboards |
| `alerting.md` | Setting up alerts and notification channels |
| `datasources.md` | Connecting Grafana to data sources |

## Monitoring Stack Architecture
```
Application → Prometheus (scrape metrics) → Grafana (visualize)
Application → Fluentd/Filebeat (ship logs) → Elasticsearch → Kibana (search logs)
AWS/OCI    → CloudWatch/OCI Monitoring → Grafana (via plugin)
```

## What to Monitor (The Four Golden Signals)
```
1. LATENCY    — How long requests take (p50, p95, p99)
2. TRAFFIC    — How many requests per second
3. ERRORS     — Error rate (4xx, 5xx responses)
4. SATURATION — How full is the system (CPU, memory, disk, connections)
```

## Prometheus Metrics in Your App

### Python (FastAPI)
```python
# Install: pip install prometheus-fastapi-instrumentator
from prometheus_fastapi_instrumentator import Instrumentator

app = FastAPI()
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Custom metrics
from prometheus_client import Counter, Histogram, Gauge

REQUEST_COUNT = Counter(
    'myapp_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'myapp_request_duration_seconds',
    'Request latency',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

ACTIVE_CONNECTIONS = Gauge(
    'myapp_active_connections',
    'Number of active connections'
)
```

### Node.js (Express/React Backend)
```typescript
import promClient from 'prom-client';

// Enable default metrics
promClient.collectDefaultMetrics({ prefix: 'myapp_' });

// Custom metrics
const httpRequestDuration = new promClient.Histogram({
  name: 'myapp_http_request_duration_seconds',
  help: 'Duration of HTTP requests',
  labelNames: ['method', 'route', 'status_code'],
  buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5],
});

// Expose /metrics endpoint
app.get('/metrics', async (req, res) => {
  res.set('Content-Type', promClient.register.contentType);
  res.end(await promClient.register.metrics());
});
```

## Prometheus Scrape Config
```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'myapp'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        target_label: __address__
        regex: (.+)
        replacement: ${1}:$1

  - job_name: 'node-exporter'
    static_configs:
      - targets: ['node-exporter:9100']

  # For non-K8s (direct scrape)
  - job_name: 'myapp-direct'
    static_configs:
      - targets: ['myapp:8000']
    metrics_path: /metrics
```
