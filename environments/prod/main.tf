module "server" {
  count = var.server_enabled ? 1 : 0

  source = "../../modules/server"

  environment = "prod"

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

  environment = "prod"

  name      = var.volume_name
  size      = var.volume_size
  server_id = one(module.server[*].id)

  delete_protection = true
}
