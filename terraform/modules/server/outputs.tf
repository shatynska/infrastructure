output "id" {
  description = "ID of the created server."
  value       = hcloud_server.this.id
}

output "ipv4_address" {
  description = "Public IPv4 address of the created server."
  value       = hcloud_server.this.ipv4_address
}

output "firewall_id" {
  description = "ID of the firewall attached to the server."
  value       = hcloud_firewall.this.id
}
