# Kubernetes Security

## Pod Security — Apply to Every Deployment

### Security Context (Mandatory for All Pods)
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  template:
    spec:
      securityContext:
        runAsNonRoot: true
        runAsUser: 1000
        runAsGroup: 1000
        fsGroup: 1000
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: myapp
          image: myregistry/myapp:1.2.3    # NEVER :latest
          securityContext:
            allowPrivilegeEscalation: false
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
          resources:
            limits:
              cpu: "1"
              memory: "512Mi"
            requests:
              cpu: "250m"
              memory: "128Mi"
          volumeMounts:
            - name: tmp
              mountPath: /tmp
      volumes:
        - name: tmp
          emptyDir:
            sizeLimit: 100Mi
```

## RBAC — Least Privilege Access

### Service Account Per App (Never Use Default)
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: myapp-sa
  namespace: myapp-prod
  annotations:
    # For AWS EKS — IRSA (IAM Roles for Service Accounts)
    eks.amazonaws.com/role-arn: arn:aws:iam::ACCOUNT:role/myapp-role
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: myapp-role
  namespace: myapp-prod
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list"]           # Only what's needed
  - apiGroups: [""]
    resources: ["secrets"]
    resourceNames: ["myapp-secrets"]  # Specific secrets only
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: myapp-binding
  namespace: myapp-prod
subjects:
  - kind: ServiceAccount
    name: myapp-sa
roleRef:
  kind: Role
  name: myapp-role
  apiGroup: rbac.authorization.k8s.io
```

## Network Policies (Default Deny + Allow Specific)

### Deny All by Default
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: myapp-prod
spec:
  podSelector: {}
  policyTypes:
    - Ingress
    - Egress
```

### Allow Specific Traffic
```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-myapp-traffic
  namespace: myapp-prod
spec:
  podSelector:
    matchLabels:
      app: myapp
  policyTypes:
    - Ingress
    - Egress
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: nginx-ingress
      ports:
        - port: 8000
          protocol: TCP
  egress:
    - to:
        - podSelector:
            matchLabels:
              app: postgres
      ports:
        - port: 5432
          protocol: TCP
    - to:                          # Allow DNS
        - namespaceSelector: {}
      ports:
        - port: 53
          protocol: UDP
        - port: 53
          protocol: TCP
    - to:                          # Allow HTTPS out
        - ipBlock:
            cidr: 0.0.0.0/0
      ports:
        - port: 443
          protocol: TCP
```

## Image Security
```yaml
# Use image pull secrets for private registries
apiVersion: v1
kind: Secret
metadata:
  name: registry-credentials
type: kubernetes.io/dockerconfigjson
data:
  .dockerconfigjson: <base64-encoded-docker-config>
---
# Reference in pod spec
spec:
  imagePullSecrets:
    - name: registry-credentials
  containers:
    - name: myapp
      image: myregistry/myapp:1.2.3@sha256:abc123  # Pin by digest in prod
```

## Pod Disruption Budgets (Prevent Accidental Outage)
```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: myapp-pdb
  namespace: myapp-prod
spec:
  minAvailable: 1
  selector:
    matchLabels:
      app: myapp
```

## Secrets in K8s
```
Rule: NEVER store secrets in plain Kubernetes Secrets committed to git.
Use one of:
1. External Secrets Operator (syncs from AWS SM / OCI Vault)
2. Sealed Secrets (encrypted before committing)
3. SOPS + age/gpg (encrypted in git, decrypted at deploy)

See: security/auth-and-secrets.md for full patterns
```

## K8s Security Checklist
```
□ All pods run as non-root with read-only root filesystem
□ All containers have resource limits
□ RBAC configured with least privilege
□ Network policies enforce default-deny
□ No use of default service account
□ Image tags pinned (no :latest)
□ Pod security standards enforced (Restricted)
□ Secrets managed externally (not plain K8s Secrets in git)
□ Pod disruption budgets set for production workloads
□ Audit logging enabled on the cluster
```
