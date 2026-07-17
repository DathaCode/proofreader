# Oracle Cloud Infrastructure (OCI) Terraform Modules

## VCN Module (Virtual Cloud Network — OCI's VPC)
```hcl
# modules/oci-vcn/main.tf
resource "oci_core_vcn" "main" {
  compartment_id = var.compartment_id
  display_name   = "${var.project}-${var.environment}-vcn"
  cidr_blocks    = [var.vcn_cidr]
  dns_label      = replace("${var.project}${var.environment}", "-", "")
}

# Internet Gateway (public access)
resource "oci_core_internet_gateway" "main" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project}-${var.environment}-igw"
  enabled        = true
}

# NAT Gateway (private subnet internet access)
resource "oci_core_nat_gateway" "main" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project}-${var.environment}-nat"
}

# Service Gateway (access OCI services without internet)
resource "oci_core_service_gateway" "main" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project}-${var.environment}-sgw"
  services {
    service_id = data.oci_core_services.all_services.services[0].id
  }
}

# Public Subnet
resource "oci_core_subnet" "public" {
  compartment_id    = var.compartment_id
  vcn_id            = oci_core_vcn.main.id
  display_name      = "${var.project}-${var.environment}-public"
  cidr_block        = cidrsubnet(var.vcn_cidr, 4, 0)
  route_table_id    = oci_core_route_table.public.id
  security_list_ids = [oci_core_security_list.public.id]
  dns_label         = "public"
}

# Private Subnet
resource "oci_core_subnet" "private" {
  compartment_id             = var.compartment_id
  vcn_id                     = oci_core_vcn.main.id
  display_name               = "${var.project}-${var.environment}-private"
  cidr_block                 = cidrsubnet(var.vcn_cidr, 4, 1)
  route_table_id             = oci_core_route_table.private.id
  security_list_ids          = [oci_core_security_list.private.id]
  prohibit_public_ip_on_vnic = true
  dns_label                  = "private"
}

# Route Tables
resource "oci_core_route_table" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project}-public-rt"
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_internet_gateway.main.id
  }
}

resource "oci_core_route_table" "private" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project}-private-rt"
  route_rules {
    destination       = "0.0.0.0/0"
    network_entity_id = oci_core_nat_gateway.main.id
  }
}

# Security Lists
resource "oci_core_security_list" "public" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project}-public-sl"

  ingress_security_rules {
    protocol = "6"  # TCP
    source   = "0.0.0.0/0"
    tcp_options { min = 443; max = 443 }
  }
  ingress_security_rules {
    protocol = "6"
    source   = "0.0.0.0/0"
    tcp_options { min = 80; max = 80 }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}

resource "oci_core_security_list" "private" {
  compartment_id = var.compartment_id
  vcn_id         = oci_core_vcn.main.id
  display_name   = "${var.project}-private-sl"

  ingress_security_rules {
    protocol = "6"
    source   = var.vcn_cidr   # Only from within VCN
    tcp_options { min = 8000; max = 8000 }
  }
  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
  }
}
```

## Compute Module (ARM Instances — Always Free Eligible)
```hcl
# modules/oci-compute/main.tf

# Always Free ARM instances (4 OCPU, 24GB RAM total!)
resource "oci_core_instance" "app" {
  count               = var.instance_count
  compartment_id      = var.compartment_id
  availability_domain = data.oci_identity_availability_domains.ads.availability_domains[0].name
  display_name        = "${var.project}-${var.environment}-${count.index + 1}"
  shape               = var.shape

  dynamic "shape_config" {
    for_each = var.shape == "VM.Standard.A1.Flex" ? [1] : []
    content {
      ocpus         = var.ocpus
      memory_in_gbs = var.memory_gb
    }
  }

  source_details {
    source_type = "image"
    source_id   = var.image_id
  }

  create_vnic_details {
    subnet_id        = var.subnet_id
    assign_public_ip = var.is_public
    nsg_ids          = var.nsg_ids
  }

  metadata = {
    ssh_authorized_keys = var.ssh_public_key
    user_data = base64encode(templatefile("${path.module}/cloud-init.yml", {
      project     = var.project
      environment = var.environment
    }))
  }

  freeform_tags = {
    Project     = var.project
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# modules/oci-compute/variables.tf
variable "shape" {
  type    = string
  default = "VM.Standard.A1.Flex"  # Always Free ARM
}
variable "ocpus" {
  type    = number
  default = 2       # 2 of 4 free OCPUs
}
variable "memory_gb" {
  type    = number
  default = 12      # 12 of 24 free GB
}
```

## Autonomous Database Module (Always Free)
```hcl
# modules/oci-autonomous-db/main.tf
resource "oci_database_autonomous_database" "main" {
  compartment_id           = var.compartment_id
  display_name             = "${var.project}-${var.environment}-adb"
  db_name                  = replace("${var.project}${var.environment}", "-", "")
  db_workload              = "OLTP"                # or "DW" for data warehouse
  is_free_tier             = var.environment != "prod"  # Free for dev/staging!
  compute_count            = var.is_free_tier ? 1 : var.compute_count
  data_storage_size_in_gbs = var.is_free_tier ? 20 : var.storage_gb
  admin_password           = var.admin_password
  is_auto_scaling_enabled  = !var.is_free_tier

  # Network
  subnet_id          = var.is_private ? var.subnet_id : null
  nsg_ids            = var.is_private ? var.nsg_ids : null

  # Security
  whitelisted_ips = var.is_private ? null : var.allowed_ips

  freeform_tags = {
    Project     = var.project
    Environment = var.environment
  }
}

# Get connection strings
output "connection_strings" {
  value = oci_database_autonomous_database.main.connection_strings
}

output "db_name" {
  value = oci_database_autonomous_database.main.db_name
}
```

## OKE Module (Oracle Kubernetes Engine)
```hcl
# modules/oci-oke/main.tf
resource "oci_containerengine_cluster" "main" {
  compartment_id     = var.compartment_id
  kubernetes_version = var.kubernetes_version
  name               = "${var.project}-${var.environment}"
  vcn_id             = var.vcn_id

  endpoint_config {
    is_public_ip_enabled = var.environment != "prod"
    subnet_id            = var.control_plane_subnet_id
  }

  options {
    service_lb_subnet_ids = [var.lb_subnet_id]
    kubernetes_network_config {
      pods_cidr     = "10.244.0.0/16"
      services_cidr = "10.96.0.0/16"
    }
  }
}

# Node Pool — ARM for cost savings
resource "oci_containerengine_node_pool" "main" {
  cluster_id         = oci_containerengine_cluster.main.id
  compartment_id     = var.compartment_id
  kubernetes_version = var.kubernetes_version
  name               = "${var.project}-${var.environment}-pool"

  node_shape = "VM.Standard.A1.Flex"   # ARM — cost effective
  node_shape_config {
    ocpus         = var.node_ocpus
    memory_in_gbs = var.node_memory_gb
  }

  node_config_details {
    size = var.node_count
    dynamic "placement_configs" {
      for_each = data.oci_identity_availability_domains.ads.availability_domains
      content {
        availability_domain = placement_configs.value.name
        subnet_id           = var.worker_subnet_id
      }
    }
  }

  node_source_details {
    image_id    = var.node_image_id
    source_type = "IMAGE"
  }

  initial_node_labels {
    key   = "environment"
    value = var.environment
  }
}
```

## Load Balancer Module (Always Free Eligible)
```hcl
# modules/oci-lb/main.tf
resource "oci_load_balancer_load_balancer" "main" {
  compartment_id = var.compartment_id
  display_name   = "${var.project}-${var.environment}-lb"
  shape          = "flexible"
  shape_details {
    minimum_bandwidth_in_mbps = 10    # Free tier = 10 Mbps
    maximum_bandwidth_in_mbps = var.environment == "prod" ? 100 : 10
  }
  subnet_ids     = [var.public_subnet_id]
  is_private     = false
}

resource "oci_load_balancer_backend_set" "app" {
  load_balancer_id = oci_load_balancer_load_balancer.main.id
  name             = "${var.project}-backend"
  policy           = "ROUND_ROBIN"

  health_checker {
    protocol            = "HTTP"
    url_path            = "/health"
    port                = var.app_port
    interval_ms         = 30000
    timeout_in_millis   = 10000
    retries             = 3
    return_code         = 200
  }
}
```
