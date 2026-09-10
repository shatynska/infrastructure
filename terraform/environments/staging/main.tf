module "server" {
  count = var.server_enabled ? 1 : 0

  source = "../../modules/server"

  environment = "staging"

  name        = var.name
  server_type = var.server_type
  image       = var.image
  location    = var.location

  ssh_key_id        = hcloud_ssh_key.this.id
  ssh_allowed_cidrs = var.ssh_allowed_cidrs
  web_allowed_cidrs = var.web_allowed_cidrs

  # Both false, and both deliberately unlike prod. Rebuilding staging is
  # what staging is for -- it carries destroy_policy_gate: false in its
  # pipeline.yml for the same reason -- and provider-level deletion
  # protection would make that unreachable. Backups protect nothing here:
  # staging holds nothing this repository cannot recreate, which is a
  # property the change that puts applications on it must preserve
  # deliberately rather than spend by not noticing.
  delete_protection = false
  backups           = false
}

module "volume" {
  # The volume has no location of its own -- it can only be created
  # attached to the server, so its count depends on both toggles, not
  # volume_enabled alone. Same coupling prod's has, for the same reason.
  count = var.volume_enabled && var.server_enabled ? 1 : 0

  source = "../../modules/volume"

  environment = "staging"

  name      = var.volume_name
  size      = var.volume_size
  server_id = one(module.server[*].id)

  delete_protection = false
}
