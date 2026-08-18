# One-time import: this SSH key (Hetzner id 117088533, name
# "shatynska@helen") was already registered in the Hetzner project before
# this Terraform setup existed, using the same public key material now in
# terraform.tfvars. Hetzner enforces SSH key uniqueness on key content, not
# name, so a plain `apply` tried to create a duplicate and was rejected
# (409 uniqueness_error). This import block brings the existing key under
# Terraform management instead.
#
# Safe to delete after the next successful apply — an import block is a
# one-time instruction, not an ongoing requirement.
import {
  to = module.server.hcloud_ssh_key.this
  id = "117088533"
}
