# Grafana Dashboards

## Essential Dashboard: Application Overview
```json
{
  "title": "MyApp Overview",
  "panels": [
    {
      "title": "Request Rate",
      "type": "timeseries",
      "targets": [{ "expr": "rate(myapp_requests_total[5m])" }]
    },
    {
      "title": "Error Rate (%)",
      "type": "stat",
      "targets": [{
        "expr": "100 * rate(myapp_requests_total{status=~'5..'}[5m]) / rate(myapp_requests_total[5m])"
      }]
    },
    {
      "title": "P95 Latency",
      "type": "timeseries",
      "targets": [{
        "expr": "histogram_quantile(0.95, rate(myapp_request_duration_seconds_bucket[5m]))"
      }]
    },
    {
      "title": "Active Pods",
      "type": "stat",
      "targets": [{
        "expr": "count(kube_pod_status_phase{namespace='myapp-prod', phase='Running'})"
      }]
    }
  ]
}
```

## Key PromQL Queries

### Application Metrics
```promql
# Request rate (per second)
rate(myapp_requests_total[5m])

# Error rate percentage
100 * rate(myapp_requests_total{status=~"5.."}[5m]) / rate(myapp_requests_total[5m])

# P50, P95, P99 latency
histogram_quantile(0.50, rate(myapp_request_duration_seconds_bucket[5m]))
histogram_quantile(0.95, rate(myapp_request_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(myapp_request_duration_seconds_bucket[5m]))

# Request rate by endpoint
sum by (endpoint) (rate(myapp_requests_total[5m]))
```

### Infrastructure Metrics
```promql
# CPU usage per pod
rate(container_cpu_usage_seconds_total{namespace="myapp-prod"}[5m])

# Memory usage per pod (MB)
container_memory_usage_bytes{namespace="myapp-prod"} / 1024 / 1024

# Disk usage
node_filesystem_avail_bytes / node_filesystem_size_bytes * 100

# Network I/O
rate(container_network_receive_bytes_total{namespace="myapp-prod"}[5m])
```

## Dashboard Provisioning (as Code)
```yaml
# monitoring/grafana/provisioning/dashboards/dashboards.yml
apiVersion: 1
providers:
  - name: 'default'
    orgId: 1
    folder: 'MyApp'
    type: file
    disableDeletion: true
    editable: false
    options:
      path: /var/lib/grafana/dashboards
      foldersFromFilesStructure: true
```

## Recommended Community Dashboards (Import by ID)
```
Node Exporter:     1860
Kubernetes Cluster: 6417
Nginx Ingress:     9614
PostgreSQL:        9628
Redis:             11835
Docker:            893
```

---

# Grafana Alerting

## Alert Rules
```yaml
# monitoring/grafana/provisioning/alerting/alerts.yml
apiVersion: 1
groups:
  - orgId: 1
    name: myapp-alerts
    folder: MyApp
    interval: 1m
    rules:
      - uid: high-error-rate
        title: High Error Rate
        condition: C
        data:
          - refId: A
            queryType: ''
            model:
              expr: 100 * rate(myapp_requests_total{status=~"5.."}[5m]) / rate(myapp_requests_total[5m])
        for: 5m
        annotations:
          summary: "Error rate above 5% for 5 minutes"
        labels:
          severity: critical

      - uid: high-latency
        title: High P95 Latency
        condition: C
        data:
          - refId: A
            model:
              expr: histogram_quantile(0.95, rate(myapp_request_duration_seconds_bucket[5m]))
        for: 5m
        annotations:
          summary: "P95 latency above 2 seconds"
        labels:
          severity: warning

      - uid: pod-restart
        title: Pod Restarting
        condition: C
        data:
          - refId: A
            model:
              expr: increase(kube_pod_container_status_restarts_total{namespace="myapp-prod"}[1h])
        for: 0s
        annotations:
          summary: "Pod has restarted in the last hour"
        labels:
          severity: warning
```

## Notification Channels
```yaml
# monitoring/grafana/provisioning/alerting/contactpoints.yml
apiVersion: 1
contactPoints:
  - orgId: 1
    name: slack-critical
    receivers:
      - uid: slack-critical
        type: slack
        settings:
          url: ${SLACK_WEBHOOK_URL}
          recipient: "#alerts-critical"
          title: '{{ .CommonLabels.alertname }}'
          text: '{{ .CommonAnnotations.summary }}'

  - orgId: 1
    name: email-warning
    receivers:
      - uid: email-warning
        type: email
        settings:
          addresses: your-email@example.com
```

---

# Grafana Data Sources

## Provisioning Data Sources (as Code)
```yaml
# monitoring/grafana/provisioning/datasources/datasources.yml
apiVersion: 1
datasources:
  # Prometheus (primary metrics)
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
    jsonData:
      httpMethod: POST
      timeInterval: '15s'

  # Elasticsearch (logs — connects to Kibana stack)
  - name: Elasticsearch
    type: elasticsearch
    access: proxy
    url: http://elasticsearch:9200
    jsonData:
      index: "myapp-logs-*"
      timeField: "@timestamp"
      esVersion: "8.0.0"

  # CloudWatch (AWS metrics)
  - name: CloudWatch
    type: cloudwatch
    jsonData:
      authType: default      # Uses EC2 instance role or IRSA
      defaultRegion: us-east-1

  # PostgreSQL (direct query)
  - name: PostgreSQL
    type: postgres
    url: postgres:5432
    database: myapp
    user: grafana_reader      # Read-only user!
    secureJsonData:
      password: ${GRAFANA_DB_PASSWORD}
    jsonData:
      sslmode: require
      postgresVersion: 1600
```
