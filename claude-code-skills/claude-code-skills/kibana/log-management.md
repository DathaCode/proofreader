# Log Management

## Log Retention Strategy (Cost Optimized)
```
Environment  | Hot (fast search) | Warm (slower)  | Delete
-------------|-------------------|----------------|--------
dev          | 3 days            | -              | 3 days
staging      | 7 days            | -              | 7 days
prod         | 7 days            | 30 days        | 90 days
audit        | 30 days           | 365 days       | never (compliance)
```

## ILM Policy (Index Lifecycle Management)
```json
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
          },
          "set_priority": { "priority": 100 }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "shrink": { "number_of_shards": 1 },
          "forcemerge": { "max_num_segments": 1 },
          "set_priority": { "priority": 50 },
          "readonly": {}
        }
      },
      "cold": {
        "min_age": "30d",
        "actions": {
          "set_priority": { "priority": 0 },
          "freeze": {}
        }
      },
      "delete": {
        "min_age": "90d",
        "actions": {
          "delete": {}
        }
      }
    }
  }
}
```

## Request ID Tracing (Correlate Logs Across Services)

### Python Middleware
```python
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
import structlog

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
        # Bind request_id to all logs in this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            endpoint=str(request.url.path),
        )
        
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

# Now every log line automatically includes request_id, method, endpoint
logger.info("processing_order", order_id=456)
# Output: {"event": "processing_order", "order_id": 456, "request_id": "abc-123", "method": "POST", "endpoint": "/api/orders"}
```

### TypeScript Middleware
```typescript
import { v4 as uuidv4 } from 'uuid';
import { AsyncLocalStorage } from 'async_hooks';

const asyncLocalStorage = new AsyncLocalStorage<{ requestId: string }>();

app.use((req, res, next) => {
  const requestId = req.headers['x-request-id'] as string || uuidv4();
  res.setHeader('X-Request-ID', requestId);
  asyncLocalStorage.run({ requestId }, () => next());
});

// In your logger
const getRequestId = () => asyncLocalStorage.getStore()?.requestId || 'unknown';
```

## Log Filtering (Reduce Noise and Cost)

### Exclude Health Check Logs
```python
# In your logging config, filter out health check noise
class HealthCheckFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return '/health' not in message and '/readiness' not in message

# Apply filter
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
```

### Filebeat Filtering
```yaml
# filebeat.yml — drop health check logs before shipping
processors:
  - drop_event:
      when:
        or:
          - contains:
              message: "/health"
          - contains:
              message: "/readiness"
          - contains:
              message: "/metrics"
```

## Log Volume Estimation (For Cost Planning)
```
Rule of thumb:
- 1 request = ~500 bytes of log (structured JSON)
- 1000 RPS = ~43 GB/day of logs
- 100 RPS = ~4.3 GB/day
- 10 RPS = ~430 MB/day

Elasticsearch storage:
- Hot nodes: SSD, expensive
- Warm nodes: HDD, cheaper
- Cold/Frozen: Cheapest (or use S3 snapshots)

Cost optimization:
1. Filter out noise before shipping (health checks, debug logs in prod)
2. Use ILM to move old data to cheaper storage
3. Set aggressive retention for non-prod
4. Sample high-volume debug logs instead of shipping all
```

## Elasticsearch Alerting (Kibana Alerts)
```
Create alert in Kibana → Alerts and Insights → Rules:

Rule 1: High Error Rate
  Index: myapp-logs-*
  Condition: count() where level:"error" > 50 in last 5 minutes
  Action: Send to Slack #alerts-critical

Rule 2: Specific Error Pattern
  Index: myapp-logs-*
  Condition: count() where event:"database_connection_failed" > 0 in last 1 minute
  Action: Send to Slack #alerts-critical + Email

Rule 3: New Error Type
  Index: myapp-logs-*
  Condition: unique count of error_type > usual in last 1 hour
  Action: Send to Slack #alerts-warning
```

## Log Security Rules
```
NEVER log:
  - Passwords or password hashes
  - API keys, tokens, secrets
  - Full credit card numbers (mask: ****1234)
  - Social security numbers or government IDs
  - Full email addresses in high-volume logs (mask: u***@example.com)
  - Request/response bodies containing PII
  - Health information (HIPAA)

ALWAYS log:
  - Request IDs (for tracing)
  - User IDs (not usernames/emails in high-volume)
  - Timestamps
  - Log levels
  - Event names (structured)
  - Error types and codes
  - Duration/latency
  - HTTP status codes
```
