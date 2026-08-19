# Non-secret prod configuration. Committed per the Version Control
# Excludes State and Secrets requirement — CI needs these values present
# in a clean checkout.

name        = "main-server"
server_type = "cx33"
image       = "ubuntu-26.04"
location    = "hel1"

ssh_public_key    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMeSWD47lN9AUVvOF2/7llxkBY0WWDgmAA1VwgIdhQsW"
ssh_allowed_cidrs = ["176.104.184.0/24"]
web_allowed_cidrs = ["0.0.0.0/0"]

server_enabled = true

volume_enabled = true
volume_name    = "production_data"
volume_size    = 10
