# Owned here, not by modules/server: an SSH key is a login credential
# with a lifecycle independent of any particular server instance — it
# should outlive the server being toggled off and on. See the
# prod-server-lifecycle-toggle change's design.md for the full reasoning.
#
# This key (Hetzner id 117088533) predates this Terraform setup — it was
# the operator's personal key, imported into Terraform under
# modules/server (see the now-deleted import.tf) before being relocated
# here.
resource "hcloud_ssh_key" "this" {
  name       = "prod"
  public_key = var.ssh_public_key

  labels = {
    environment = "prod"
    managed_by  = "terraform"
  }
}

# One-time relocation: this resource used to live inside the server
# module (module.server.hcloud_ssh_key.this) before modules/server
# stopped owning SSH keys. `moved` tells Terraform this is the same
# real-world object at a new address — no destroy, no recreate, no
# re-import. Safe to delete once the next apply has run.
moved {
  from = module.server.hcloud_ssh_key.this
  to   = hcloud_ssh_key.this
}
