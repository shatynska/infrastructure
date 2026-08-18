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

  # Temporarily false to allow decommissioning the server (see the
  # decommission PR that follows this one) — Hetzner's API refuses a
  # delete while this is true, and the provider doesn't reliably handle
  # that itself (see design.md Decision 7 / task 4.6's finding). Restore
  # to true if/when a server is recreated here.
  delete_protection = false
  backups           = true
}
