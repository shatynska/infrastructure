output "server_id" {
  description = "ID of the prod server, or null if server_enabled is false."
  value       = one(module.server[*].id)
}

output "server_ipv4_address" {
  description = "Public IPv4 address of the prod server, or null if server_enabled is false."
  value       = one(module.server[*].ipv4_address)
}
