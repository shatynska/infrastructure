locals {
  labels = merge(
    {
      environment = var.environment
      managed_by  = "terraform"
    },
    var.labels
  )
}

# Default-deny inbound: only the rules declared here are allowed in.
# Outbound traffic is unrestricted by omitting any "out" rule.
resource "hcloud_firewall" "this" {
  name   = "${var.environment}-${var.name}"
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
