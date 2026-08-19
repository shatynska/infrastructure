variable "environment" {
  description = "Environment name this volume belongs to (e.g. \"prod\"). Applied as the `environment` label."
  type        = string

  validation {
    condition     = length(trimspace(var.environment)) > 0
    error_message = "environment must not be empty."
  }
}

variable "name" {
  description = "Name of the volume."
  type        = string
}

variable "size" {
  description = "Size of the volume in GB."
  type        = number
}

variable "server_id" {
  description = "ID of the hcloud_server this volume attaches to at creation. This module never sets `location` (see the volume module's design), so the provider requires either a location or an attached server — server_id must always be supplied and non-empty; there is no unattached-volume mode."
  type        = string
  nullable    = false

  validation {
    condition     = length(trimspace(var.server_id)) > 0
    error_message = "server_id must not be empty — this module has no location of its own, so the volume can only be created attached to a server."
  }
}

variable "delete_protection" {
  description = "Whether to enable Hetzner's server-side delete protection on this volume. Parameterized (not a literal lifecycle.prevent_destroy) so this module stays reusable by environments that must remain destroyable, e.g. a future staging environment."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Additional labels to merge onto the volume, in addition to the environment and managed_by labels applied automatically."
  type        = map(string)
  default     = {}
}
