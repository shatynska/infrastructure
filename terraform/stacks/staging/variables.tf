variable "name" {
  description = "Name of the staging server."
  type        = string
}

variable "server_type" {
  description = "Hetzner Cloud server type (e.g. \"cx22\"). Staging runs roughly half prod's tier; the exact current name is read from the Hetzner console rather than assumed, since no local credential here can confirm it."
  type        = string
}

variable "image" {
  description = "Hetzner Cloud image name or ID (e.g. \"ubuntu-24.04\"). Matches prod's: a stack that rehearses prod on a different image rehearses something else."
  type        = string
}

variable "location" {
  description = "Hetzner Cloud location (e.g. \"fsn1\"). The data volume takes its location from the server it attaches to, so this is the location of both."
  type        = string
}

variable "ssh_public_key" {
  description = "Public key material for staging SSH access. Not secret. The same operator key prod uses — a separate pair would be a second private key to hold for no gain, on a host this repository can recreate entirely."
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "Source CIDRs allowed to reach the staging server over SSH. Must not be 0.0.0.0/0 or ::/0; staging is no wider than prod here."
  type        = list(string)
}

variable "web_allowed_cidrs" {
  description = "Source CIDRs allowed to reach the staging server over HTTP/HTTPS. Empty by default (no web rule), and empty is what staging ships with until a change puts something behind those ports."
  type        = list(string)
  default     = []
}

variable "server_enabled" {
  description = "Whether the staging server should exist. Set false to decommission without losing configuration — every other value here and in terraform.tfvars stays in place, ready to re-enable. This is also the only rollback for this stack that does not orphan resources, and the way to stop paying for staging without deleting its configuration."
  type        = bool
  default     = true
}

variable "volume_enabled" {
  description = "Whether the staging data volume should exist. The volume has no location of its own — it can only exist attached to the staging server — so its actual effective state is volume_enabled AND server_enabled; disabling the server also removes the volume even if this stays true."
  type        = bool
  default     = true
}

variable "volume_name" {
  description = "Name of the staging data volume. Deliberately the same name prod's carries: Hetzner volume names are unique per project, not globally, so a dedicated project frees the name — and the same name means the same on-host mount path, which is what keeps platform/docker-compose.yml's hardcoded /mnt/main-data/... paths correct for both stacks."
  type        = string
}

variable "volume_size" {
  description = "Size of the staging data volume in GB."
  type        = number
}
