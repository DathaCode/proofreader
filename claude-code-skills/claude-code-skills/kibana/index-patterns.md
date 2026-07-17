# Index Patterns and Mappings

## Index Naming Strategy
```
myapp-logs-YYYY.MM.DD       ← Application logs (daily rotation)
myapp-metrics-YYYY.MM.DD    ← Application metrics
myapp-audit-YYYY.MM.DD      ← Security/audit logs
infra-logs-YYYY.MM.DD       ← Infrastructure logs (nginx, system)
```

## Index Template (Apply Before Shipping Logs)
```json
PUT _index_template/myapp-logs
{
  "index_patterns": ["myapp-logs-*"],
  "priority": 100,
  "template": {
    "settings": {
      "number_of_shards": 1,
      "number_of_replicas": 0,
      "index.lifecycle.name": "myapp-logs-policy",
      "index.lifecycle.rollover_alias": "myapp-logs"
    },
    "mappings": {
      "properties": {
        "@timestamp": { "type": "date" },
        "level": { "type": "keyword" },
        "event": { "type": "keyword" },
        "message": { "type": "text" },
        "user_id": { "type": "keyword" },
        "request_id": { "type": "keyword" },
        "endpoint": { "type": "keyword" },
        "method": { "type": "keyword" },
        "status_code": { "type": "integer" },
        "duration_ms": { "type": "float" },
        "ip": { "type": "ip" },
        "error": { "type": "text" },
        "error_type": { "type": "keyword" },
        "environment": { "type": "keyword" },
        "service": { "type": "keyword" },
        "kubernetes": {
          "properties": {
            "namespace": { "type": "keyword" },
            "pod_name": { "type": "keyword" },
            "container_name": { "type": "keyword" },
            "node_name": { "type": "keyword" }
          }
        }
      }
    }
  }
}
```

## Field Type Guide
```
keyword  — exact match, aggregation, filtering (event names, IDs, status codes)
text     — full-text search (messages, error descriptions)
date     — timestamps
integer  — whole numbers (status codes, counts)
float    — decimals (duration, amounts)
ip       — IP addresses (supports CIDR queries)
boolean  — true/false flags
geo_point — latitude/longitude (if tracking locations)
```

## Creating Index Patterns in Kibana
```
1. Stack Management → Index Patterns
2. Create Index Pattern
3. Enter pattern: myapp-logs-*
4. Select time field: @timestamp
5. Save

Repeat for:
- myapp-audit-* (time field: @timestamp)
- infra-logs-*  (time field: @timestamp)
```

## Common KQL Queries by Index

### Application Logs (myapp-logs-*)
```
# All errors in production
level: "error" AND environment: "prod"

# Specific user's activity
user_id: "user_123" AND NOT endpoint: "/health"

# Slow requests by endpoint
duration_ms > 1000 AND method: "GET"

# Failed API calls to external services
event: "external_api_call" AND status_code >= 400

# Text search in error messages
error: "connection refused" OR error: "timeout"
```

### Audit Logs (myapp-audit-*)
```
# Failed login attempts
event: "login_failed"

# Permission denied events
event: "permission_denied" AND user_id: *

# All admin actions
role: "admin" AND event: ("create_*" OR "delete_*" OR "update_*")
```

## Useful Elasticsearch API Queries
```bash
# Check cluster health
curl http://elasticsearch:9200/_cluster/health?pretty

# List all indices with size
curl http://elasticsearch:9200/_cat/indices?v&s=store.size:desc

# Check index mapping
curl http://elasticsearch:9200/myapp-logs-2024.01.15/_mapping?pretty

# Delete old indices (careful!)
curl -X DELETE http://elasticsearch:9200/myapp-logs-2023.12.*

# Count documents
curl http://elasticsearch:9200/myapp-logs-*/_count?pretty

# Search API
curl -X GET "http://elasticsearch:9200/myapp-logs-*/_search?pretty" \
  -H 'Content-Type: application/json' \
  -d '{
    "query": {
      "bool": {
        "must": [
          { "term": { "level": "error" } },
          { "range": { "@timestamp": { "gte": "now-1h" } } }
        ]
      }
    },
    "sort": [{ "@timestamp": "desc" }],
    "size": 20
  }'
```
