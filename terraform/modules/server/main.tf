locals {
  # Caller labels FIRST and the axes SECOND, so a caller cannot override an
  # axis. Consistent Resource Labeling
  # (openspec/specs/iac-safety-hardening/spec.md) obliges every resource to
  # carry one label per axis its stack is identified on; a caller-supplied
  # `tenant` or `environment` winning the merge would satisfy the merge and
  # defeat the obligation, and it would do so silently -- the plan is clean and
  # the wrong value is visible only in the Hetzner console.
  labels = merge(
    var.labels,
    {
      tenant      = var.tenant
      environment = var.environment
      managed_by  = "terraform"
    }
  )
}

# Default-deny inbound: only the rules declared here are allowed in.
# Outbound traffic is unrestricted by omitting any "out" rule.
#
# ITS NAME IS AN INPUT, NOT AN EXPRESSION OVER THE SERVER'S. It used to be
# "<environment>-<name>", which after the stack rename would read
# `production-main-production` -- the stack's name with its environment half in
# front of it. Deriving it from `var.tenant` instead would produce the right
# string today and assert something false: that a stack has one firewall and
# that its name is the tenant's. A firewall is project-local and is
# distinguished from a second one by rank, so the caller names it. See the
# change rename-the-stacks-and-their-resources, design.md decision 4.
resource "hcloud_firewall" "this" {
  name   = var.firewall_name
  labels = local.labels

  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "22"
    source_ips = var.ssh_allowed_cidrs
  }

  # HTTP/HTTPS are opt-in: no rule is created unless the caller sets
  # web_allowed_cidrs, so a server with no web service stays SSH-only.
  dynamic "rule" {
    for_each = length(var.web_allowed_cidrs) > 0 ? [80, 443] : []
    content {
      direction  = "in"
      protocol   = "tcp"
      port       = tostring(rule.value)
      source_ips = var.web_allowed_cidrs
    }
  }
}

resource "hcloud_server" "this" {
  name        = var.name
  server_type = var.server_type
  image       = var.image
  location    = var.location
  labels      = local.labels

  # Providing a key at creation means Hetzner never sets a root
  # password, so password authentication is never available. The key
  # itself is owned by the caller (see var.ssh_key_id's description),
  # not by this module.
  ssh_keys     = [var.ssh_key_id]
  firewall_ids = [hcloud_firewall.this.id]

  backups = var.backups

  delete_protection  = var.delete_protection
  rebuild_protection = var.delete_protection
}
