# Kubernetes Skill

## Purpose
Container orchestration for deploying, scaling, and managing applications on AWS EKS and Oracle OKE.

## When to Activate
- Deploying applications to Kubernetes
- Writing or editing manifests, Helm charts, or Kustomize overlays
- Debugging pod, service, or ingress issues
- Setting up networking, storage, or RBAC
- Scaling or updating deployments
- Setting up monitoring in K8s

## Sub-Skills
| File | When to Read |
|------|-------------|
| `manifests.md` | Writing deployments, services, configmaps, ingress |
| `helm-charts.md` | Creating or using Helm charts for reusable deployments |
| `networking.md` | Services, ingress, network policies, DNS |
| `troubleshooting.md` | Debugging pods, services, deployments, networking |

## Also Read
- `security/k8s-security.md` — Pod security, RBAC, network policies
- `docker/SKILL.md` — Container building for K8s
- `grafana/SKILL.md` — Monitoring K8s clusters
- `cost-reducer/cloud-and-infra.md` — K8s cost optimization

## Core K8s Rules
1. **Always set resource requests AND limits** — prevents noisy neighbors and OOM kills
2. **Always use liveness and readiness probes** — enables auto-healing
3. **Always use namespaces** — isolate environments and applications
4. **Never use :latest tag** — always pin image versions
5. **Always use a dedicated service account** — never the default SA
6. **Always set pod disruption budgets** — for production workloads
7. **Use labels consistently** — for selection, filtering, and monitoring
8. **Externalize config** — use ConfigMaps and Secrets, not baked-in values
9. **Use rolling updates** — zero-downtime deployments
10. **Monitor everything** — Prometheus metrics from every service

## Namespace Strategy
```
myapp-dev         ← Development environment
myapp-staging     ← Staging environment
myapp-prod        ← Production environment
monitoring        ← Grafana, Prometheus, Alertmanager
logging           ← ELK/EFK stack
ingress-nginx     ← Ingress controller
cert-manager      ← TLS certificate management
```

## Essential kubectl Commands
```bash
# Context management
kubectl config get-contexts
kubectl config use-context my-cluster
kubectl config set-context --current --namespace=myapp-prod

# Pod operations
kubectl get pods -n myapp-prod
kubectl describe pod POD_NAME -n myapp-prod
kubectl logs POD_NAME -n myapp-prod -f --tail=100
kubectl logs POD_NAME -n myapp-prod --previous    # Crashed pod logs
kubectl exec -it POD_NAME -n myapp-prod -- /bin/sh
kubectl port-forward POD_NAME 8000:8000 -n myapp-prod

# Deployment operations
kubectl get deployments -n myapp-prod
kubectl rollout status deployment/myapp -n myapp-prod
kubectl rollout history deployment/myapp -n myapp-prod
kubectl rollout undo deployment/myapp -n myapp-prod           # Rollback
kubectl rollout undo deployment/myapp --to-revision=3 -n myapp-prod  # Specific revision
kubectl scale deployment/myapp --replicas=3 -n myapp-prod

# Debugging
kubectl get events -n myapp-prod --sort-by='.lastTimestamp'
kubectl top pods -n myapp-prod                    # Resource usage
kubectl top nodes                                  # Node resource usage

# Apply manifests
kubectl apply -f manifest.yaml
kubectl apply -k overlays/production/             # Kustomize
kubectl diff -f manifest.yaml                     # Preview changes

# Delete resources
kubectl delete -f manifest.yaml
kubectl delete pod POD_NAME -n myapp-prod --grace-period=0  # Force delete
```
