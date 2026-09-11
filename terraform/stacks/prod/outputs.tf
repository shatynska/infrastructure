output "server_id" {
  description = "ID of the prod server, or null if server_enabled is false."
  value       = one(module.server[*].id)
}

output "server_ipv4_address" {
  description = "Public IPv4 address of the prod server, or null if server_enabled is false."
  value       = one(module.server[*].ipv4_address)
}

output "volume_id" {
  description = "ID of the prod data volume, or null if volume_enabled is false (or server_enabled is false, since the volume can't exist without the server)."
  value       = one(module.volume[*].id)
}

output "volume_linux_device" {
  description = "Device path of the prod data volume as seen inside the server's guest OS, or null if the volume doesn't currently exist."
  value       = one(module.volume[*].linux_device)
}
