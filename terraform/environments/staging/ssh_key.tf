# Owned here, not by modules/server: an SSH key is a login credential with
# a lifecycle independent of any particular server instance — it should
# outlive the server being toggled off and on. Same placement prod's has,
# for the same reason.
#
# Created fresh in staging's own Hetzner project, so unlike prod's there is
# no `moved` block: prod's records a one-time relocation of a key that
# predates this Terraform setup, which has no staging analogue.
#
# The key material is the same operator public key prod uses. Names are
# unique per project, so `staging` here collides with nothing.
resource "hcloud_ssh_key" "this" {
  name       = "staging"
  public_key = var.ssh_public_key

  labels = {
    environment = "staging"
    managed_by  = "terraform"
  }
}
