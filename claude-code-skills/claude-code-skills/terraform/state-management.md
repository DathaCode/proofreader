# Terraform State Management

## Remote Backend Setup

### AWS S3 Backend (Recommended for AWS Projects)
```hcl
# backend.tf — in each environment directory
terraform {
  backend "s3" {
    bucket         = "mycompany-terraform-state"
    key            = "myapp/dev/terraform.tfstate"    # Unique per environment
    region         = "us-east-1"
    encrypt        = true
    dynamodb_table = "terraform-state-lock"           # State locking
  }
}
```

### Bootstrap the Backend (Run Once, Before Everything Else)
```hcl
# global/terraform-backend/main.tf
# Apply this FIRST with local state, then migrate

resource "aws_s3_bucket" "terraform_state" {
  bucket = "mycompany-terraform-state"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "terraform_state" {
  bucket                  = aws_s3_bucket.terraform_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_dynamodb_table" "terraform_lock" {
  name         = "terraform-state-lock"
  billing_mode = "PAY_PER_REQUEST"    # Cost effective for low usage
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
```

### OCI Object Storage Backend
```hcl
terraform {
  backend "s3" {
    bucket                      = "terraform-state"
    key                         = "myapp/dev/terraform.tfstate"
    region                      = "us-ashburn-1"
    endpoint                    = "https://<namespace>.compat.objectstorage.<region>.oraclecloud.com"
    skip_region_validation      = true
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    force_path_style            = true
    encrypt                     = true
  }
}
```

## State Organization Strategy

### One State File Per Environment Per Project
```
terraform-state-bucket/
├── myapp/
│   ├── dev/terraform.tfstate
│   ├── staging/terraform.tfstate
│   └── prod/terraform.tfstate
├── another-app/
│   ├── dev/terraform.tfstate
│   └── prod/terraform.tfstate
└── global/
    ├── iam/terraform.tfstate
    ├── dns/terraform.tfstate
    └── ecr/terraform.tfstate
```

### Referencing Other State Files (Data Source)
```hcl
# In myapp/dev — reference the global VPC state
data "terraform_remote_state" "vpc" {
  backend = "s3"
  config = {
    bucket = "mycompany-terraform-state"
    key    = "networking/dev/terraform.tfstate"
    region = "us-east-1"
  }
}

# Use outputs from the other state
resource "aws_ecs_service" "app" {
  network_configuration {
    subnets = data.terraform_remote_state.vpc.outputs.private_subnet_ids
  }
}
```

## Common State Operations

### Import Existing Resource
```bash
# Import a resource that was created manually or by another tool
terraform import aws_instance.app i-0abc123def456
terraform import 'aws_security_group.app' sg-0abc123def456
terraform import 'module.vpc.aws_vpc.main' vpc-0abc123def456

# For OCI resources
terraform import oci_core_instance.app ocid1.instance.oc1.iad.xxx
```

### Move Resources Between States
```bash
# Remove from source state
terraform state rm 'module.old_module.aws_instance.app'

# Import into target state (from the target directory)
terraform import 'module.new_module.aws_instance.app' i-0abc123def456
```

### Rename a Resource (Without Destroying)
```hcl
# In your .tf file, add a moved block:
moved {
  from = aws_instance.old_name
  to   = aws_instance.new_name
}

# Then run terraform plan — it will show a move, not destroy+create
```

### Taint and Replace
```bash
# Force recreation of a resource
terraform taint aws_instance.app        # Deprecated method
terraform apply -replace=aws_instance.app  # Preferred method
```

## State Safety Rules
```
1. NEVER edit .tfstate files directly
2. NEVER store state in Git
3. ALWAYS enable state locking
4. ALWAYS enable state encryption
5. ALWAYS enable bucket versioning (for recovery)
6. ALWAYS run plan before apply
7. Use CI/CD for production state changes — avoid manual applies
8. Keep state files small — split large infrastructure into multiple states
9. Regular state backups (S3 versioning handles this)
10. Audit who runs terraform (CloudTrail for AWS)
```

## Recovering from State Issues
```bash
# State file corrupted or lost? Recover from S3 versioning:
aws s3api list-object-versions \
  --bucket mycompany-terraform-state \
  --prefix myapp/prod/terraform.tfstate

# Restore a previous version:
aws s3api get-object \
  --bucket mycompany-terraform-state \
  --key myapp/prod/terraform.tfstate \
  --version-id VERSION_ID \
  recovered.tfstate

# Force unlock stuck state:
terraform force-unlock LOCK_ID
# ONLY after confirming no other process is running!
```
