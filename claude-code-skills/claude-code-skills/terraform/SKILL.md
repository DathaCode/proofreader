# Terraform Skill

## Purpose
Infrastructure as Code for provisioning and managing AWS and Oracle Cloud Infrastructure. Single source of truth for all cloud resources.

## When to Activate
- Provisioning any cloud resource (compute, network, database, storage, etc.)
- Modifying existing infrastructure
- Setting up new environments (dev/staging/prod)
- Migrating resources between clouds
- Debugging infrastructure issues
- Cost optimization of cloud resources

## Sub-Skills
| File | When to Read |
|------|-------------|
| `aws-modules.md` | Provisioning any AWS resource |
| `oracle-modules.md` | Provisioning any OCI resource |
| `state-management.md` | Setting up backends, workspaces, state operations |
| `best-practices.md` | Code structure, naming, variables, outputs |

## Also Read
- `security/cloud-security.md` — IAM, encryption, network security
- `cost-reducer/cloud-and-infra.md` — Right-sizing, free tiers, spot instances

## Core Terraform Rules
1. **Never modify state manually** — use `terraform state` commands or `terraform import`
2. **Never apply without plan** — always run `terraform plan` first
3. **Remote state only** — never use local state for shared infrastructure
4. **Lock state** — enable state locking to prevent concurrent modifications
5. **Pin provider versions** — avoid surprises from provider updates
6. **Use modules** — DRY principle, reuse common patterns
7. **Separate environments** — use workspaces or separate state files
8. **Tag everything** — every resource must have standard tags
9. **Use variables** — never hardcode values
10. **Sensitive outputs** — mark sensitive values with `sensitive = true`

## Project Structure
```
infrastructure/
├── modules/                    # Reusable modules
│   ├── aws-vpc/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── README.md
│   ├── aws-ecs/
│   ├── aws-rds/
│   ├── oci-vcn/
│   ├── oci-compute/
│   └── oci-autonomous-db/
│
├── environments/               # Environment-specific configs
│   ├── dev/
│   │   ├── main.tf            # Uses modules with dev values
│   │   ├── variables.tf
│   │   ├── terraform.tfvars
│   │   ├── backend.tf
│   │   └── outputs.tf
│   ├── staging/
│   └── prod/
│
├── global/                     # Shared resources (IAM, DNS, etc.)
│   ├── iam/
│   ├── route53/
│   └── ecr/
│
└── scripts/
    ├── plan.sh
    └── apply.sh
```

## Required Provider Setup
```hcl
# versions.tf — in every environment directory
terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"        # Pin major version
    }
    oci = {
      source  = "oracle/oci"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

provider "oci" {
  tenancy_ocid = var.tenancy_ocid
  region       = var.oci_region
}
```

## Quick Reference Commands
```bash
# Initialize
terraform init
terraform init -upgrade          # Upgrade providers

# Plan
terraform plan -out=tfplan       # Save plan to file
terraform plan -target=aws_instance.app  # Plan specific resource

# Apply
terraform apply tfplan           # Apply saved plan
terraform apply -auto-approve    # Skip approval (CI/CD only)

# State management
terraform state list             # List all managed resources
terraform state show aws_instance.app  # Show resource details
terraform import aws_instance.app i-1234567890  # Import existing resource
terraform state rm aws_instance.app  # Remove from state (doesn't destroy)

# Destroy
terraform plan -destroy          # Preview destruction
terraform destroy -target=aws_instance.temp  # Destroy specific resource

# Format and validate
terraform fmt -recursive         # Format all files
terraform validate               # Check syntax
```
