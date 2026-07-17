# Terraform Best Practices

## File Organization (Per Module/Environment)
```
module-or-env/
├── main.tf          # Primary resources
├── variables.tf     # Input variables (ALL inputs here)
├── outputs.tf       # Output values (ALL outputs here)
├── versions.tf      # Provider and terraform version constraints
├── backend.tf       # Backend configuration (environments only)
├── data.tf          # Data sources (optional, for complex modules)
├── locals.tf        # Local values (optional)
└── README.md        # What this module does, inputs, outputs
```

## Variable Best Practices
```hcl
# variables.tf — always include type, description, and validation

variable "project" {
  type        = string
  description = "Project name, used as prefix for all resources"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]+$", var.project))
    error_message = "Project name must be lowercase alphanumeric with hyphens."
  }
}

variable "environment" {
  type        = string
  description = "Deployment environment"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "instance_class" {
  type        = string
  description = "RDS instance class"
  default     = "db.t3.micro"     # Default to cheapest
}

# NEVER put default values for secrets
variable "db_password" {
  type        = string
  description = "Database admin password"
  sensitive   = true    # Hides from plan/apply output
}
```

## Naming Conventions
```hcl
# Resources: {project}-{environment}-{purpose}
# Examples:
#   myapp-prod-vpc
#   myapp-dev-api-sg
#   myapp-staging-db

locals {
  name_prefix = "${var.project}-${var.environment}"

  common_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
    Owner       = "solo-dev"
  }
}

# Use the prefix consistently
resource "aws_vpc" "main" {
  tags = merge(local.common_tags, {
    Name = "${local.name_prefix}-vpc"
  })
}
```

## Output Best Practices
```hcl
# outputs.tf — output everything other modules/states might need

output "vpc_id" {
  description = "ID of the VPC"
  value       = aws_vpc.main.id
}

output "private_subnet_ids" {
  description = "IDs of private subnets"
  value       = aws_subnet.private[*].id
}

# Mark sensitive outputs
output "db_endpoint" {
  description = "RDS endpoint"
  value       = aws_db_instance.main.endpoint
  sensitive   = true
}
```

## Conditional Resources
```hcl
# Create resource only in certain environments
resource "aws_cloudwatch_log_group" "detailed" {
  count = var.environment == "prod" ? 1 : 0
  name  = "/app/${var.project}/detailed"
}

# Use for_each for multiple similar resources
resource "aws_security_group_rule" "app_ingress" {
  for_each = {
    http  = { port = 80,  cidr = "0.0.0.0/0" }
    https = { port = 443, cidr = "0.0.0.0/0" }
    app   = { port = 8000, cidr = var.vpc_cidr }
  }

  type              = "ingress"
  security_group_id = aws_security_group.app.id
  from_port         = each.value.port
  to_port           = each.value.port
  protocol          = "tcp"
  cidr_blocks       = [each.value.cidr]
}
```

## Lifecycle Management
```hcl
resource "aws_instance" "app" {
  lifecycle {
    # Prevent accidental destruction of production
    prevent_destroy = var.environment == "prod" ? true : false

    # Ignore changes made outside Terraform
    ignore_changes = [
      tags["LastUpdatedBy"],
      user_data,
    ]

    # Create new before destroying old (zero-downtime)
    create_before_destroy = true
  }
}
```

## tfvars by Environment
```hcl
# environments/dev/terraform.tfvars
project         = "myapp"
environment     = "dev"
aws_region      = "us-east-1"
vpc_cidr        = "10.0.0.0/16"
instance_class  = "db.t3.micro"
desired_count   = 1

# environments/prod/terraform.tfvars
project         = "myapp"
environment     = "prod"
aws_region      = "us-east-1"
vpc_cidr        = "10.1.0.0/16"
instance_class  = "db.t3.medium"
desired_count   = 2
```

## Pre-Apply Checklist
```
□ terraform fmt -check (code formatted?)
□ terraform validate (syntax correct?)
□ terraform plan reviewed (no unexpected changes?)
□ No secrets in code or tfvars committed to git?
□ State backend configured and locked?
□ Resource naming follows convention?
□ All variables have types, descriptions, and validations?
□ Sensitive values marked as sensitive?
□ Production resources have deletion protection?
□ Tags applied to all resources?
```
