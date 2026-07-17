# Kibana Dashboards

## Setting Up Your First Dashboard

### Step 1: Create Index Pattern
```
Kibana → Stack Management → Index Patterns → Create Index Pattern
Pattern: myapp-logs-*
Time field: @timestamp
```

### Step 2: Essential Visualizations

#### Error Rate Over Time (Line Chart)
```
Visualization → Lens → Line
Index: myapp-logs-*
Metric: Count
Filter: level: "error"
Break down by: Date Histogram (@timestamp, auto interval)
```

#### Top Errors by Endpoint (Bar Chart)
```
Visualization → Lens → Bar Horizontal
Index: myapp-logs-*
Metric: Count
Filter: level: "error"
Break down by: Top values (endpoint, 10)
```

#### Status Code Distribution (Donut)
```
Visualization → Lens → Donut
Index: myapp-logs-*
Metric: Count
Slice by: Top values (status_code, 10)
```

#### Log Volume Over Time (Area Chart)
```
Visualization → Lens → Area
Index: myapp-logs-*
Metric: Count
Break down by: Date Histogram (@timestamp, auto)
Color by: Top values (level)
```

## Dashboard Layout (Recommended)
```
┌─────────────────────────────────────────────────┐
│  Error Count (Metric) │ Warn Count │ Total Logs  │  ← Top Row: KPIs
├─────────────────────────────────────────────────┤
│  Log Volume Over Time (Area — colored by level)  │  ← Trend
├────────────────────────┬────────────────────────┤
│  Top Errors by         │  Status Code           │  ← Breakdown
│  Endpoint (Bar)        │  Distribution (Donut)  │
├─────────────────────────────────────────────────┤
│  Recent Error Logs (Saved Search / Table)         │  ← Detail
└─────────────────────────────────────────────────┘
```

## Saved Searches (Create These First)

### All Errors
```
Name: "All Errors"
Query: level: "error" OR level: "critical"
Columns: @timestamp, event, endpoint, user_id, message
Sort: @timestamp descending
```

### Slow Requests
```
Name: "Slow Requests (>2s)"
Query: duration_ms > 2000 AND NOT endpoint: "/health"
Columns: @timestamp, endpoint, duration_ms, user_id, method
Sort: duration_ms descending
```

### Authentication Events
```
Name: "Auth Events"
Query: event: ("user_login" OR "user_logout" OR "login_failed" OR "token_expired")
Columns: @timestamp, event, user_id, ip, method
Sort: @timestamp descending
```

### Payment Events
```
Name: "Payment Events"
Query: event: ("payment_*")
Columns: @timestamp, event, user_id, amount, status, error
Sort: @timestamp descending
```

## Dashboard Filters (Add to Every Dashboard)
```
- Environment: field=environment, values=[dev, staging, prod]
- Service: field=kubernetes.container.name
- Time Range: Quick select (Last 1h, 4h, 24h, 7d)
- Log Level: field=level, values=[debug, info, warning, error, critical]
```

## Export/Import Dashboards
```bash
# Export via API
curl -X GET "http://kibana:5601/api/saved_objects/_export" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  -d '{"type": ["dashboard", "visualization", "search", "index-pattern"]}' \
  > dashboards-export.ndjson

# Import via API
curl -X POST "http://kibana:5601/api/saved_objects/_import" \
  -H "kbn-xsrf: true" \
  --form file=@dashboards-export.ndjson
```
