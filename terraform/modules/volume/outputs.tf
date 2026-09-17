output "id" {
  description = "ID of the created volume."
  value       = hcloud_volume.this.id
}

output "linux_device" {
  description = "Device path of the volume as seen inside the attached server's guest OS."
  value       = hcloud_volume.this.linux_device
}
