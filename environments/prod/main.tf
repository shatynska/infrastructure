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
