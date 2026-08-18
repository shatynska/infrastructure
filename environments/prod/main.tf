module "server" {
  source = "../../modules/server"

  environment = "prod"

  name        = var.name
  server_type = var.server_type
  image       = var.image
  location    = var.location

  ssh_public_key    = var.ssh_public_key
  ssh_allowed_cidrs = var.ssh_allowed_cidrs
  web_allowed_cidrs = var.web_allowed_cidrs

  # delete_protection = true is a prod-specific choice, not the module
  # default consumers should inherit blindly. See design.md Decision 7.
  delete_protection = true
  backups           = true
}
