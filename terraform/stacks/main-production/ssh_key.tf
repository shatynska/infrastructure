# Owned here, not by modules/server: an SSH key is a login credential
# with a lifecycle independent of any particular server instance — it
# should outlive the server being toggled off and on. See the
# prod-server-lifecycle-toggle change's design.md for the full reasoning.
#
# This key (Hetzner id 117088533) predates this Terraform setup — it was
# the operator's personal key, imported into Terraform under
# modules/server (see the now-deleted import.tf) before being relocated
# here.
#
# NAMED ON THE IDENTITY AXIS, NOT THE RANK ONE. A key is distinguished by what
# it authenticates, never by which of several it is: a second key here would be
# a deploy key, a CI key, or another person's, and `main` would say nothing
# about any of them. This one is the operator's root credential, whose
# workstation half is `~/.ssh/<company>-root`.
resource "hcloud_ssh_key" "this" {
  name       = "operator"
  public_key = var.ssh_public_key

  # Declared here rather than by a module, and inside the labeling obligation
  # all the same -- see Consistent Resource Labeling
  # (openspec/specs/iac-safety-hardening/spec.md), whose scenario "An SSH key a
  # stack owns directly is labeled" exists because a resource outside a module
  # is the one a labeling sweep misses.
  labels = {
    tenant      = "main"
    environment = "production"
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
