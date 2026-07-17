# Kubernetes Networking

## Service Types
```yaml
# ClusterIP (default) — internal only
apiVersion: v1
kind: Service
metadata:
  name: myapp-internal
spec:
  type: ClusterIP
  selector:
    app: myapp
  ports:
    - port: 80
      targetPort: 8000

# NodePort — expose on each node (dev/testing)
# Accessible at <NodeIP>:30080
apiVersion: v1
kind: Service
metadata:
  name: myapp-nodeport
spec:
  type: NodePort
  selector:
    app: myapp
  ports:
    - port: 80
      targetPort: 8000
      nodePort: 30080

# LoadBalancer — cloud provider LB (AWS ALB/NLB, OCI LB)
apiVersion: v1
kind: Service
metadata:
  name: myapp-lb
  annotations:
    service.beta.kubernetes.io/aws-load-balancer-type: "nlb"
    service.beta.kubernetes.io/aws-load-balancer-internal: "true"
spec:
  type: LoadBalancer
  selector:
    app: myapp
  ports:
    - port: 80
      targetPort: 8000
```

## Ingress with TLS (HTTPS)
```yaml
# First: install cert-manager ClusterIssuer
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: your-email@example.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
---
# Then: use in Ingress
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: myapp
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - myapp.com
        - api.myapp.com
      secretName: myapp-tls
  rules:
    - host: myapp.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp-frontend
                port:
                  number: 80
    - host: api.myapp.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: myapp-api
                port:
                  number: 80
```

## DNS Within Cluster
```
# Service DNS format:
<service-name>.<namespace>.svc.cluster.local

# Examples:
myapp.myapp-prod.svc.cluster.local          → app service
postgres.myapp-prod.svc.cluster.local        → database
redis.myapp-prod.svc.cluster.local           → cache
elasticsearch.logging.svc.cluster.local      → ELK in logging namespace

# Short form (same namespace):
myapp        → works if caller is in same namespace
postgres     → works if caller is in same namespace
```

---

# Kubernetes Troubleshooting

## Pod Issues

### Pod Not Starting
```bash
# Step 1: Check pod status
kubectl get pods -n myapp-prod

# Step 2: Describe pod for events
kubectl describe pod POD_NAME -n myapp-prod
# Look for: Events section at bottom

# Step 3: Check logs
kubectl logs POD_NAME -n myapp-prod
kubectl logs POD_NAME -n myapp-prod --previous  # If crashed

# Step 4: Check resource availability
kubectl top nodes
kubectl describe node NODE_NAME
```

### Common Pod States and Fixes
```
CrashLoopBackOff:
  → App crashes on startup
  → Check: logs --previous
  → Fix: Fix app code, check env vars, check secrets exist

ImagePullBackOff:
  → Can't pull container image
  → Check: image name/tag correct? registry auth configured?
  → Fix: verify image exists, check imagePullSecrets

Pending:
  → No node can schedule the pod
  → Check: kubectl describe pod — events section
  → Fix: insufficient resources → scale nodes or reduce requests
         node selector/affinity doesn't match → fix selectors
         PVC not bound → check storage class

OOMKilled:
  → Out of memory
  → Check: kubectl describe pod — last state reason
  → Fix: increase memory limits or fix memory leak

CreateContainerConfigError:
  → ConfigMap or Secret referenced but doesn't exist
  → Check: kubectl describe pod — events
  → Fix: create the missing ConfigMap/Secret
```

### Service Not Reachable
```bash
# Step 1: Verify service exists and has endpoints
kubectl get svc myapp -n myapp-prod
kubectl get endpoints myapp -n myapp-prod
# If endpoints is empty → labels don't match

# Step 2: Check labels match
kubectl get pods -n myapp-prod --show-labels
kubectl get svc myapp -n myapp-prod -o yaml | grep selector -A5

# Step 3: Test from within cluster
kubectl run debug --rm -it --image=busybox -n myapp-prod -- sh
wget -qO- http://myapp:80/health
nslookup myapp.myapp-prod.svc.cluster.local

# Step 4: Check network policies
kubectl get networkpolicy -n myapp-prod
```

### Ingress Not Working
```bash
# Step 1: Check ingress controller is running
kubectl get pods -n ingress-nginx

# Step 2: Check ingress resource
kubectl describe ingress myapp -n myapp-prod

# Step 3: Check ingress controller logs
kubectl logs -n ingress-nginx -l app.kubernetes.io/name=ingress-nginx

# Step 4: Check TLS certificate
kubectl get certificate -n myapp-prod
kubectl describe certificate myapp-tls -n myapp-prod
```

## Quick Debug Commands
```bash
# Run a debug pod
kubectl run debug --rm -it --image=nicolaka/netshoot -n myapp-prod -- bash

# Inside debug pod:
curl http://myapp:80/health           # Test service
nslookup myapp                        # Test DNS
traceroute myapp                      # Test network path
dig myapp.myapp-prod.svc.cluster.local  # Full DNS lookup

# Check what's using resources
kubectl top pods -n myapp-prod --sort-by=memory
kubectl top pods -n myapp-prod --sort-by=cpu

# Get all events (most recent last)
kubectl get events -n myapp-prod --sort-by='.lastTimestamp' | tail -20

# Force delete stuck pod
kubectl delete pod POD_NAME -n myapp-prod --grace-period=0 --force
```
