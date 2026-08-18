variable "name" {
  description = "Name of the prod server."
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
  description = "Public key material for prod SSH access. Not secret, but has no default — it depends on the SSH key pair created/selected in task 1.7 and must be supplied once that exists."
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "Source CIDRs allowed to reach the prod server over SSH. Depends on the decision recorded for task 1.6 — must not be 0.0.0.0/0 or ::/0."
  type        = list(string)
}
