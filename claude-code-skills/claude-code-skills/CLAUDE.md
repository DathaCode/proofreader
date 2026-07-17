# CLAUDE.md — Master Configuration for Claude Code

## Who I Am
I am a solo full-stack developer, architect, and DevOps/Cloud engineer.
I build, deploy, and operate ALL my applications myself on **Oracle Cloud (OCI)** and **AWS** infrastructure.
I use **Claude Code** as my AI pair-programmer for every part of the development lifecycle.

## My Tech Stack
- **Languages**: Python, TypeScript, React (JSX/TSX)
- **Containerization**: Docker, Docker Compose
- **Orchestration**: Kubernetes (EKS on AWS, OKE on Oracle)
- **Infrastructure as Code**: Terraform (multi-cloud: AWS + OCI)
- **CI/CD**: GitHub Actions
- **Monitoring**: Grafana (metrics/dashboards), Kibana (logs/search)
- **Cloud Providers**: AWS (primary), Oracle Cloud Infrastructure (secondary)

## How to Use This Knowledge Base

### Folder Structure
```
claude-code-skills/
├── CLAUDE.md                  ← You are here (master config)
│
├── security/                  ← Security patterns for everything I build
│   ├── SKILL.md
│   ├── auth-and-secrets.md
│   ├── web-security.md
│   ├── docker-security.md
│   ├── cloud-security.md
│   └── k8s-security.md
│
├── self-healing/              ← Teaches Claude to learn from mistakes
│   ├── SKILL.md
│   ├── pattern-recognition.md
│   ├── memory-management.md
│   └── skill-creation-guide.md
│
├── cost-reducer/              ← Find cost optimization opportunities
│   ├── SKILL.md
│   ├── cloud-and-infra.md
│   ├── services-and-finops.md
│   └── code-level-savings.md
│
├── researcher/                ← Validate info before implementing
│   └── SKILL.md
│
├── docker/                    ← Container skills
│   ├── SKILL.md
│   ├── dockerfile-patterns.md
│   ├── compose-patterns.md
│   └── optimization.md
│
├── terraform/                 ← IaC for AWS + Oracle
│   ├── SKILL.md
│   ├── aws-modules.md
│   ├── oracle-modules.md
│   ├── state-management.md
│   └── best-practices.md
│
├── github/                    ← Git workflows + CI/CD
│   ├── SKILL.md
│   ├── ci-cd-pipelines.md
│   ├── branch-strategy.md
│   └── actions-workflows.md
│
├── kubernetes/                ← K8s orchestration
│   ├── SKILL.md
│   ├── manifests.md
│   ├── helm-charts.md
│   ├── networking.md
│   └── troubleshooting.md
│
├── grafana/                   ← Metrics & dashboards
│   ├── SKILL.md
│   ├── dashboards.md
│   ├── alerting.md
│   └── datasources.md
│
├── kibana/                    ← Logs & search
│   ├── SKILL.md
│   ├── dashboards.md
│   ├── index-patterns.md
│   └── log-management.md
│
├── python/                    ← Python development
│   ├── SKILL.md
│   ├── project-structure.md
│   ├── fastapi-patterns.md
│   ├── testing.md
│   └── packaging.md
│
├── react/                     ← Frontend development
│   ├── SKILL.md
│   ├── component-patterns.md
│   ├── state-management.md
│   └── testing.md
│
└── typescript/                ← TypeScript patterns
    ├── SKILL.md
    ├── type-patterns.md
    ├── project-setup.md
    └── best-practices.md
```

### Rules for Claude Code
1. **ALWAYS** check the relevant SKILL.md before writing any code or config
2. **ALWAYS** apply security/ guidelines to every piece of work
3. **ALWAYS** consider cost-reducer/ when provisioning infrastructure
4. **ALWAYS** use self-healing/ patterns when something fails
5. **ALWAYS** validate with researcher/ before using unfamiliar tools or approaches
6. When I say "deploy this", follow: docker/ → terraform/ → github/ → kubernetes/ pipeline
7. When I say "monitor this", follow: grafana/ + kibana/ setup
8. Never hardcode secrets — always reference security/auth-and-secrets.md
9. Default to the cheapest viable option unless I say otherwise
10. I am a solo operator — keep things simple, automatable, and maintainable by one person

### My Naming Conventions
- GitHub repos: `kebab-case` (e.g., `my-awesome-app`)
- Docker images: `my-registry/app-name:version`
- Terraform modules: `module-provider-resource` (e.g., `module-aws-vpc`)
- K8s namespaces: `app-name-env` (e.g., `myapp-prod`)
- Branches: `feature/description`, `fix/description`, `hotfix/description`

### My Environment Labels
- `dev` — local development
- `staging` — pre-production testing
- `prod` — production
