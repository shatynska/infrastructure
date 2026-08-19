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

variable "ssh_key_id" {
  description = "ID of an existing hcloud_ssh_key resource to attach to the server for SSH access. Providing a key at creation means Hetzner never sets a root password, so password authentication is never available. This module does not create or own the key — its lifecycle (a login credential) is independent of any particular server instance, so the caller owns it. See the prod-server-lifecycle-toggle change's design.md for why."
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

variable "web_allowed_cidrs" {
  description = "Source CIDRs allowed to reach the server over HTTP (80) and HTTPS (443). Empty by default — no web rule is created, so a server with no web service stays SSH-only. Set to [\"0.0.0.0/0\"] for a public-facing web service."
  type        = list(string)
  default     = []
}

variable "delete_protection" {
  description = "Whether to enable Hetzner's server-side delete/rebuild protection. Parameterized (not a literal lifecycle.prevent_destroy) so this module stays reusable by environments that must remain destroyable, e.g. a future staging environment. Does not reliably block `terraform destroy`/replace (see design.md decision 7 finding for task 4.6) — the CI destroy-policy gate is the actual Terraform-side guard; this only blocks deletion via the Hetzner console/API."
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
