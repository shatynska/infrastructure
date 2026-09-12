module "server" {
  count = var.server_enabled ? 1 : 0

  source = "../../modules/server"

  # The two axes this stack is identified on, each carried as a label of its
  # own rather than as a segment of a name -- see Consistent Resource Labeling
  # (openspec/specs/iac-safety-hardening/spec.md). `production` is spelled in
  # full: `prod` and `preprod` share a prefix, and this value is read by prefix
  # in more places than it is read whole.
  tenant      = "main"
  environment = "production"

  # `main`, on the rank axis. A firewall never leaves its Hetzner project, so a
  # second one here would be the extra one and would be named beside this. It is
  # passed rather than derived: the module used to build
  # "<environment>-<name>", which would now read `production-main-production`.
  firewall_name = "main"

  name        = var.name
  server_type = var.server_type
  image       = var.image
  location    = var.location

  ssh_key_id        = hcloud_ssh_key.this.id
  ssh_allowed_cidrs = var.ssh_allowed_cidrs
  web_allowed_cidrs = var.web_allowed_cidrs

  # delete_protection = true is a prod-specific choice, not the module
  # default consumers should inherit blindly. See design.md Decision 7.
  # (Was temporarily false to allow the prod-server-lifecycle-toggle
  # change's decommission — restored now that the server is being
  # recreated.)
  delete_protection = true
  backups           = true
}

module "volume" {
  # The volume has no location of its own — it can only be created
  # attached to the server, so its count depends on both toggles, not
  # volume_enabled alone. See design.md Decision 3 of the
  # add-prod-data-volume change.
  count = var.volume_enabled && var.server_enabled ? 1 : 0

  source = "../../modules/volume"

  tenant      = "main"
  environment = "production"

  name      = var.volume_name
  size      = var.volume_size
  server_id = one(module.server[*].id)

  delete_protection = true
}
