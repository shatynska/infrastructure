output "server_id" {
  description = "ID of the prod server."
  value       = module.server.id
}

output "server_ipv4_address" {
  description = "Public IPv4 address of the prod server."
  value       = module.server.ipv4_address
}
