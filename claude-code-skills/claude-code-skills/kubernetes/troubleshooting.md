# Kubernetes Troubleshooting Flowchart

## Master Debug Flowchart
```
PROBLEM: App not accessible
│
├─ Can you reach the Ingress?
│  NO → Check Ingress controller pods: kubectl get pods -n ingress-nginx
│       Check Ingress resource: kubectl describe ingress -n NAMESPACE
│       Check DNS: nslookup yourdomain.com
│       Check TLS cert: kubectl get certificate -n NAMESPACE
│
├─ Can you reach the Service internally?
│  NO → Check Service exists: kubectl get svc -n NAMESPACE
│       Check Endpoints: kubectl get endpoints -n NAMESPACE
│       If endpoints empty → Labels mismatch between Service and Pod
│       Check NetworkPolicy: kubectl get netpol -n NAMESPACE
│
├─ Are Pods running?
│  NO → Check Pod status: kubectl get pods -n NAMESPACE
│       See "Pod State Reference" below
│
├─ Are Pods healthy?
│  NO → Check probe failures: kubectl describe pod POD -n NAMESPACE
│       Check app logs: kubectl logs POD -n NAMESPACE
│       Check resources: kubectl top pod POD -n NAMESPACE
│
└─ Everything looks fine but still broken?
   → Run debug pod: kubectl run debug --rm -it --image=nicolaka/netshoot -- bash
   → curl the service from inside the cluster
   → Check if the app responds on the correct port
   → Check environment variables: kubectl exec POD -- env
```

## Node Issues
```bash
# Node not ready
kubectl get nodes
kubectl describe node NODE_NAME
# Look for: Conditions section — MemoryPressure, DiskPressure, PIDPressure

# Drain a node for maintenance
kubectl drain NODE_NAME --ignore-daemonsets --delete-emptydir-data
# After maintenance:
kubectl uncordon NODE_NAME

# Check node resources
kubectl top nodes
kubectl describe node NODE_NAME | grep -A 10 "Allocated resources"
```

## Deployment Rollback
```bash
# Check rollout status
kubectl rollout status deployment/myapp -n myapp-prod

# View history
kubectl rollout history deployment/myapp -n myapp-prod

# Rollback to previous version
kubectl rollout undo deployment/myapp -n myapp-prod

# Rollback to specific revision
kubectl rollout undo deployment/myapp --to-revision=5 -n myapp-prod

# Pause a bad rollout
kubectl rollout pause deployment/myapp -n myapp-prod
# Fix the issue, then:
kubectl rollout resume deployment/myapp -n myapp-prod
```

## Storage Issues
```bash
# PVC stuck in Pending
kubectl get pvc -n NAMESPACE
kubectl describe pvc PVC_NAME -n NAMESPACE
# Common causes:
# - StorageClass doesn't exist
# - No available PV matching the claim
# - Insufficient storage on nodes

# Check storage classes
kubectl get storageclass
```

## Common Mistakes Checklist
```
□ Port mismatch — Service targetPort must match container port
□ Label mismatch — Service selector must match Pod labels exactly
□ Namespace mismatch — resources must be in the same namespace to communicate by short name
□ Image tag wrong — verify image exists in registry
□ Secret not created — ConfigMap/Secret must exist before Pod starts
□ Probe path wrong — health check endpoint must return 200
□ Resource limits too low — app OOMKilled because memory limit is too tight
□ Read-only filesystem — app tries to write to root fs but securityContext is readOnly
□ DNS not resolving — check CoreDNS pods in kube-system
□ RBAC denied — ServiceAccount lacks permissions for the action
```
