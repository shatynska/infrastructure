variable "name" {
  description = "Name of the production server. This repository gives it the name of its stack, because a server's name reaches the tailnet and the heartbeat account, neither of which is scoped to one Hetzner project."
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
  description = "Public key material for production SSH access. Not secret, but has no default — it depends on the SSH key pair created/selected in task 1.7 and must be supplied once that exists."
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "Source CIDRs allowed to reach the production server over SSH. Depends on the decision recorded for task 1.6 — must not be 0.0.0.0/0 or ::/0."
  type        = list(string)
}

variable "web_allowed_cidrs" {
  description = "Source CIDRs allowed to reach the production server over HTTP/HTTPS. Empty by default (no web rule)."
  type        = list(string)
  default     = []
}

variable "server_enabled" {
  description = "Whether the production server should exist. Set false to decommission without losing configuration — all other values here and in terraform.tfvars stay in place, ready to re-enable."
  type        = bool
  default     = true
}

variable "volume_enabled" {
  description = "Whether the production stack's volume should exist. The volume has no location of its own — it can only exist attached to the production server — so its actual effective state is volume_enabled AND server_enabled; disabling the server also removes the volume even if this stays true. Set false to detach the volume from management without losing configuration."
  type        = bool
  default     = true
}

variable "volume_name" {
  description = "Name of the production stack's volume. Named on the rank axis (`main`) rather than for what consumes it, and independent of the path it is mounted at: the on-host device is keyed on the volume's id, not its name."
  type        = string
}

variable "volume_size" {
  description = "Size of the production stack's volume in GB."
  type        = number
}
