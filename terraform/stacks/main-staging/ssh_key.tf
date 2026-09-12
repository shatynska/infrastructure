# Owned here, not by modules/server: an SSH key is a login credential with
# a lifecycle independent of any particular server instance — it should
# outlive the server being toggled off and on. Same placement prod's has,
# for the same reason.
#
# Created fresh in staging's own Hetzner project, so unlike prod's there is
# no `moved` block: prod's records a one-time relocation of a key that
# predates this Terraform setup, which has no staging analogue.
#
# The key material is the same operator public key the production stack uses,
# and so is the name. Names are unique per project, so `operator` here collides
# with nothing -- and the two stacks naming it identically is the point: a key
# is named for what it authenticates, and this authenticates the same operator
# in both places.
resource "hcloud_ssh_key" "this" {
  name       = "operator"
  public_key = var.ssh_public_key

  # Declared here rather than by a module, and inside the labeling obligation
  # all the same -- see Consistent Resource Labeling
  # (openspec/specs/iac-safety-hardening/spec.md).
  labels = {
    tenant      = "main"
    environment = "staging"
    managed_by  = "terraform"
  }
}
