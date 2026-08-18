variable "environment" {
  description = "Environment name this server belongs to (e.g. \"prod\"). Applied as the `environment` label."
  type        = string

  validation {
    condition     = length(trimspace(var.environment)) > 0
    error_message = "environment must not be empty."
  }
}

variable "name" {
  description = "Name of the server."
  type        = string
}

variable "server_type" {
  description = "Hetzner Cloud server type (e.g. \"cx22\")."
  type        = string
}

variable "image" {
  description = "Hetzner Cloud image name or ID (e.g. \"ubuntu-24.04\")."
  type        = string
}

variable "location" {
  description = "Hetzner Cloud location (e.g. \"fsn1\")."
  type        = string
}

variable "ssh_public_key" {
  description = "Public key material (e.g. contents of an id_ed25519.pub file) used for SSH access. Providing this at creation means Hetzner never sets a root password, so password authentication is never available."
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "Source CIDRs allowed to reach the server over SSH (port 22). Must not include 0.0.0.0/0 or ::/0 — see the open question in the bootstrap-hetzner-iac design doc."
  type        = list(string)

  validation {
    condition     = length(var.ssh_allowed_cidrs) > 0
    error_message = "ssh_allowed_cidrs must not be empty — a server firewall with no SSH rule at all would lock out access; specify at least one real source CIDR."
  }

  validation {
    condition     = !contains(var.ssh_allowed_cidrs, "0.0.0.0/0") && !contains(var.ssh_allowed_cidrs, "::/0")
    error_message = "ssh_allowed_cidrs must not include 0.0.0.0/0 or ::/0 — SSH must not be exposed to the entire internet."
  }
}

variable "delete_protection" {
  description = "Whether to enable Hetzner's server-side delete/rebuild protection. Parameterized (not a literal lifecycle.prevent_destroy) so this module stays reusable by environments that must remain destroyable, e.g. a future staging environment."
  type        = bool
  default     = true
}

variable "backups" {
  description = "Whether to enable Hetzner's automatic server backups (adds a surcharge to the server price). Protects the data on disk; delete_protection only protects the resource itself."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Additional labels to merge onto every resource this module creates, in addition to the environment and managed_by labels applied automatically."
  type        = map(string)
  default     = {}
}
