# Non-secret prod configuration. Committed per the Version Control
# Excludes State and Secrets requirement — CI needs these values present
# in a clean checkout.

name        = "server"
server_type = "cx23"
image       = "ubuntu-26.04"
location    = "hel1"

ssh_public_key    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMeSWD47lN9AUVvOF2/7llxkBY0WWDgmAA1VwgIdhQsW throwaway-destroy-gate-test"
ssh_allowed_cidrs = ["176.104.184.0/24"]
web_allowed_cidrs = ["0.0.0.0/0"]

# Decommissioned — see the prod-server-lifecycle-toggle change. All other
# values above stay in place; set this back to true (or remove the line)
# to recreate the server with the same configuration — no other step
# needed, since the SSH key (see ssh_key.tf) was never tied to this toggle.
server_enabled = false
