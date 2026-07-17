# Helm Charts

## Creating a Helm Chart for Your App
```bash
# Create chart scaffold
helm create myapp
# This creates:
# myapp/
# ├── Chart.yaml
# ├── values.yaml
# ├── templates/
# │   ├── deployment.yaml
# │   ├── service.yaml
# │   ├── ingress.yaml
# │   ├── hpa.yaml
# │   ├── serviceaccount.yaml
# │   ├── _helpers.tpl
# │   └── NOTES.txt
# └── charts/
```

## values.yaml (Per-Environment)
```yaml
# values.yaml (defaults — dev)
replicaCount: 1

image:
  repository: ACCOUNT.dkr.ecr.REGION.amazonaws.com/myapp
  tag: "latest"
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 80
  targetPort: 8000

ingress:
  enabled: true
  className: nginx
  hosts:
    - host: dev.myapp.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: myapp-tls
      hosts:
        - dev.myapp.com

resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 500m
    memory: 256Mi

autoscaling:
  enabled: false

env:
  ENVIRONMENT: dev
  LOG_LEVEL: debug

secrets:
  existingSecret: myapp-secrets

probes:
  liveness:
    path: /health
    initialDelaySeconds: 30
  readiness:
    path: /health
    initialDelaySeconds: 10
```

```yaml
# values-prod.yaml (production overrides)
replicaCount: 2

image:
  tag: "1.2.3"
  pullPolicy: IfNotPresent

ingress:
  hosts:
    - host: myapp.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: myapp-prod-tls
      hosts:
        - myapp.com

resources:
  requests:
    cpu: 250m
    memory: 256Mi
  limits:
    cpu: "1"
    memory: 512Mi

autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70

env:
  ENVIRONMENT: production
  LOG_LEVEL: info
```

## Helm Commands
```bash
# Install / upgrade
helm upgrade --install myapp ./myapp \
  -n myapp-prod \
  -f myapp/values-prod.yaml \
  --set image.tag=1.2.3

# Dry run (preview)
helm upgrade --install myapp ./myapp \
  -n myapp-prod \
  -f myapp/values-prod.yaml \
  --dry-run --debug

# Template rendering (see what YAML will be generated)
helm template myapp ./myapp -f myapp/values-prod.yaml

# History and rollback
helm history myapp -n myapp-prod
helm rollback myapp 3 -n myapp-prod    # Rollback to revision 3

# List releases
helm list -n myapp-prod
helm list --all-namespaces

# Uninstall
helm uninstall myapp -n myapp-prod

# Install from repository
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install prometheus prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace \
  -f monitoring-values.yaml
```

## Common Helm Charts to Install
```bash
# Ingress Controller
helm install ingress-nginx ingress-nginx/ingress-nginx \
  -n ingress-nginx --create-namespace

# Cert Manager (TLS certificates)
helm install cert-manager jetstack/cert-manager \
  -n cert-manager --create-namespace \
  --set installCRDs=true

# Prometheus + Grafana (monitoring)
helm install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace

# External Secrets Operator (AWS/OCI secrets → K8s)
helm install external-secrets external-secrets/external-secrets \
  -n external-secrets --create-namespace

# Metrics Server (required for HPA)
helm install metrics-server metrics-server/metrics-server \
  -n kube-system
```
