# How to Use This Skills Setup with Claude Code

## Quick Start (3 Steps)

### Step 1: Copy Skills to Your Project
```bash
# Copy the entire claude-code-skills folder to your project root
cp -r claude-code-skills/ /path/to/your-project/.claude/

# Or if you want it at user level (applies to ALL projects)
cp -r claude-code-skills/ ~/.claude/
```

### Step 2: Set CLAUDE.md as Your Project Root Config
```bash
# Copy the master CLAUDE.md to your project root
cp claude-code-skills/CLAUDE.md /path/to/your-project/CLAUDE.md
```

### Step 3: Tell Claude Code to Use It
When starting Claude Code in your project, it automatically reads `CLAUDE.md` from the project root. That file references all the skill folders.

---

## Folder Structure in Your Project
```
your-project/
├── CLAUDE.md                    ← Claude Code reads this automatically
├── .claude/                     ← Skill files live here
│   ├── security/
│   ├── self-healing/
│   ├── cost-reducer/
│   ├── researcher/
│   ├── docker/
│   ├── terraform/
│   ├── github/
│   ├── kubernetes/
│   ├── grafana/
│   ├── kibana/
│   ├── python/
│   ├── react/
│   └── typescript/
├── backend/                     ← Your app code
├── frontend/
├── infrastructure/
├── docker-compose.yml
└── Dockerfile
```

---

## Prompting Strategies

### 1. Starting a New Project
```
Prompt:
"I'm starting a new SaaS application called [app-name].
Stack: Python FastAPI backend, React TypeScript frontend, PostgreSQL database.
Deployment: Docker → AWS ECS.

Set up the complete project structure following our skill files.
Include: project structure, Dockerfile, docker-compose.yml, CI/CD pipeline,
Terraform for AWS, and monitoring setup."
```

### 2. Building a Feature
```
Prompt:
"Add user authentication to my app. I need:
- JWT-based auth with login/register endpoints
- Password hashing with bcrypt
- Protected route middleware
- React login/register forms with Zustand auth store
- Tests for all endpoints

Follow our security/auth-and-secrets.md and python/fastapi-patterns.md skills."
```

### 3. Setting Up Infrastructure
```
Prompt:
"Set up the AWS infrastructure for my app using Terraform:
- VPC with public/private subnets
- ECS Fargate cluster
- RDS PostgreSQL (smallest instance for dev)
- ECR for Docker images
- S3 for file storage

Follow terraform/aws-modules.md and cost-reducer/cloud-and-infra.md.
This is for the dev environment — optimize for cost."
```

### 4. Creating CI/CD Pipeline
```
Prompt:
"Create the GitHub Actions CI/CD pipeline for my full-stack app:
- On PR: lint, type-check, test (backend + frontend), security scan
- On merge to main: build Docker image, push to ECR, deploy to staging
- Manual approval for production deploy

Follow github/ci-cd-pipelines.md and github/actions-workflows.md."
```

### 5. Setting Up Monitoring
```
Prompt:
"Set up monitoring for my production app:
- Prometheus metrics in my FastAPI app
- Grafana dashboards for the 4 golden signals
- ELK stack for centralized logging
- Structured JSON logging in my Python app
- Alert rules for high error rate and latency

Follow grafana/SKILL.md and kibana/SKILL.md."
```

### 6. Deploying to Kubernetes
```
Prompt:
"Create Kubernetes manifests for my app:
- Deployment with proper security context, probes, resource limits
- Service + Ingress with TLS (cert-manager)
- HPA for auto-scaling
- Network policies
- ConfigMap and ExternalSecret for config/secrets

Follow kubernetes/manifests.md and security/k8s-security.md."
```

### 7. Debugging an Issue
```
Prompt:
"My pod is in CrashLoopBackOff. Here's the error:
[paste error]

Follow self-healing/pattern-recognition.md to diagnose and fix this.
Don't retry the same approach if it fails — change strategy."
```

### 8. Cost Optimization Review
```
Prompt:
"Review my current Terraform infrastructure and find cost savings.
Check for: over-provisioned instances, unused resources, missing lifecycle
policies, and opportunities to use free tier or spot instances.

Follow cost-reducer/ skills for all recommendations."
```

### 9. Security Audit
```
Prompt:
"Do a security audit of my codebase. Check for:
- Hardcoded secrets
- Missing input validation
- Docker security issues
- Terraform IAM over-permissions
- Missing security headers
- K8s security context issues

Follow all files in security/ and create a report."
```

---

## Power Prompting Tips

### Reference Specific Skill Files
```
"Follow the patterns in docker/dockerfile-patterns.md for this Dockerfile"
"Use the testing approach from python/testing.md"
"Apply all checks from security/SKILL.md before finishing"
```

### Chain Multiple Skills
```
"Build this feature using:
1. python/fastapi-patterns.md for the API
2. react/component-patterns.md for the frontend
3. docker/compose-patterns.md for local dev
4. github/ci-cd-pipelines.md for the pipeline
5. security/SKILL.md for everything"
```

### Ask Claude to Self-Check
```
"Before you finish, run through:
- security/SKILL.md checklist
- cost-reducer/SKILL.md checklist
- The relevant technology skill checklist"
```

### Fix-and-Learn Loop
```
"That failed. Follow self-healing/SKILL.md:
1. Read the full error
2. Identify root cause
3. Don't retry the same approach
4. Fix it
5. Tell me what you learned for next time"
```

### Bulk Operations
```
"Apply this change across ALL my services:
- Update all Dockerfiles to follow docker/dockerfile-patterns.md
- Update all Terraform to follow terraform/best-practices.md
- Update all Python code to follow python/SKILL.md standards"
```

---

## Customizing for Your Projects

### Add Project-Specific Context to CLAUDE.md
```markdown
## Project: MyApp
- Frontend runs on port 3000
- Backend runs on port 8000
- Database: PostgreSQL 16 on port 5432
- Redis on port 6379
- AWS Account ID: 123456789012
- AWS Region: us-east-1
- OCI Tenancy: ocid1.tenancy.oc1..xxx
- OCI Region: us-ashburn-1
- Docker Registry: 123456789012.dkr.ecr.us-east-1.amazonaws.com
- Domain: myapp.com
```

### Add New Skills Over Time
When you discover a new pattern that works, create a new skill:
```
"Create a new skill file at .claude/caching/SKILL.md that documents
the Redis caching pattern we just built. Follow the format in
self-healing/skill-creation-guide.md."
```
