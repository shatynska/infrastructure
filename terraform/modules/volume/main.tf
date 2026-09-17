locals {
  # Caller labels FIRST and the axes SECOND, so a caller cannot override an
  # axis. The same merge order modules/server uses, for the reason stated
  # there.
  labels = merge(
    var.labels,
    {
      tenant      = var.tenant
      environment = var.environment
      managed_by  = "terraform"
    }
  )
}

# No `location` argument: the provider derives it from `server_id`, and
# requires the two to match — declaring both would risk a mismatch the
# provider would reject. See modules/volume's design for why `server_id`
# is therefore required rather than optional.
resource "hcloud_volume" "this" {
  name              = var.name
  size              = var.size
  server_id         = var.server_id
  delete_protection = var.delete_protection
  labels            = local.labels
}
