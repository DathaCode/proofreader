# Kibana Skill

## Purpose
Log management, search, and visualization using the Elasticsearch + Kibana (ELK) stack. Central logging hub for all applications.

## When to Activate
- Setting up centralized logging for any application
- Creating log dashboards and visualizations
- Debugging issues using application logs
- Setting up log retention and index management
- Creating Kibana saved searches and alerts

## Sub-Skills
| File | When to Read |
|------|-------------|
| `dashboards.md` | Creating Kibana dashboards and visualizations |
| `index-patterns.md` | Setting up index patterns and mappings |
| `log-management.md` | Log shipping, retention, and structured logging |

## Also Read
- `grafana/SKILL.md` — Grafana can also query Elasticsearch as a data source

## Logging Architecture
```
App (structured JSON logs)
  → stdout/stderr
  → Fluentd/Filebeat (log shipper)
  → Elasticsearch (storage + search)
  → Kibana (visualization + search UI)
```

## Structured Logging (Required in ALL Applications)

### Python Structured Logging
```python
import structlog
import logging

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),     # JSON output for ELK
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
)

logger = structlog.get_logger()

# Usage — always include context
logger.info("user_login", user_id=123, ip="1.2.3.4", method="password")
logger.error("payment_failed", user_id=123, amount=50.00, error="insufficient_funds")
logger.warning("rate_limit_hit", ip="1.2.3.4", endpoint="/api/login")
```

Output:
```json
{"event": "user_login", "user_id": 123, "ip": "1.2.3.4", "method": "password", "level": "info", "timestamp": "2024-01-15T10:30:00Z"}
```

### Node.js/TypeScript Structured Logging
```typescript
import pino from 'pino';

const logger = pino({
  level: process.env.LOG_LEVEL || 'info',
  formatters: {
    level: (label) => ({ level: label }),
  },
  timestamp: pino.stdTimeFunctions.isoTime,
});

// Usage
logger.info({ userId: 123, ip: '1.2.3.4' }, 'user_login');
logger.error({ userId: 123, amount: 50, error: 'insufficient_funds' }, 'payment_failed');
```

## Log Shipping

### Filebeat (Kubernetes)
```yaml
# filebeat-daemonset.yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: filebeat
  namespace: logging
spec:
  selector:
    matchLabels:
      app: filebeat
  template:
    spec:
      serviceAccountName: filebeat
      containers:
        - name: filebeat
          image: docker.elastic.co/beats/filebeat:8.14.0
          volumeMounts:
            - name: config
              mountPath: /usr/share/filebeat/filebeat.yml
              subPath: filebeat.yml
            - name: varlog
              mountPath: /var/log
            - name: containerlog
              mountPath: /var/lib/docker/containers
              readOnly: true
      volumes:
        - name: config
          configMap:
            name: filebeat-config
        - name: varlog
          hostPath:
            path: /var/log
        - name: containerlog
          hostPath:
            path: /var/lib/docker/containers
```

```yaml
# filebeat.yml
filebeat.autodiscover:
  providers:
    - type: kubernetes
      node: ${NODE_NAME}
      hints.enabled: true
      hints.default_config:
        type: container
        paths:
          - /var/log/containers/*-${data.kubernetes.container.id}.log

processors:
  - add_kubernetes_metadata:
      host: ${NODE_NAME}
  - decode_json_fields:
      fields: ["message"]
      target: ""
      overwrite_keys: true

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "myapp-logs-%{+yyyy.MM.dd}"
```

## Elasticsearch Index Management
```json
// Index Lifecycle Management (ILM) policy
PUT _ilm/policy/myapp-logs-policy
{
  "policy": {
    "phases": {
      "hot": {
        "min_age": "0ms",
        "actions": {
          "rollover": {
            "max_age": "1d",
            "max_size": "5gb"
          }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "shrink": { "number_of_shards": 1 },
          "forcemerge": { "max_num_segments": 1 }
        }
      },
      "delete": {
        "min_age": "30d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
```

## Useful Kibana Searches (KQL)
```
# Find errors
level: "error"

# Specific user's actions
user_id: 123 AND level: ("info" OR "error")

# Payment failures
event: "payment_failed" AND amount > 100

# Rate limit hits in last hour
event: "rate_limit_hit"

# Errors in a specific service
kubernetes.container.name: "myapp-api" AND level: "error"

# Slow requests (if you log duration)
duration_ms > 5000

# Exclude health checks
NOT endpoint: "/health"
```

## Logging Rules
```
1. ALWAYS use structured logging (JSON) — never print() or console.log() for production
2. ALWAYS include context (user_id, request_id, endpoint) in every log line
3. NEVER log secrets, passwords, tokens, or PII
4. Use appropriate log levels:
   - DEBUG: detailed diagnostic info (disable in prod)
   - INFO: normal operations (user actions, business events)
   - WARNING: unexpected but handled (rate limits, retries)
   - ERROR: failures requiring attention (unhandled exceptions, API failures)
   - CRITICAL: system-level failures (database down, out of memory)
5. Use request IDs to correlate logs across services
6. Set log retention policies (don't keep logs forever — it costs money)
7. Alert on ERROR and CRITICAL logs
```
