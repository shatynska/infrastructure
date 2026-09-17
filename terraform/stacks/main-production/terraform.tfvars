# Non-secret configuration for the main-production stack. Committed per the
# Version Control Excludes State and Secrets requirement — CI needs these
# values present in a clean checkout.

# THE SERVER TAKES ITS STACK'S NAME, and it is the one name here that leaves
# its Hetzner project. It reaches the tailnet as a machine name and the
# heartbeat account as `<inventory_hostname>-prune-host-images`, and both of
# those hold every stack a company owns — so a name unique per project is not
# unique where this one is read. The heartbeat collision is the one to fear: it
# fails green, the live host's weekly success keeping the check while another
# host's timer is dead.
name        = "main-production"
server_type = "cx33"
image       = "ubuntu-26.04"
location    = "hel1"

ssh_public_key    = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMeSWD47lN9AUVvOF2/7llxkBY0WWDgmAA1VwgIdhQsW"
ssh_allowed_cidrs = ["176.104.184.0/24"]
web_allowed_cidrs = ["0.0.0.0/0"]

server_enabled = true

volume_enabled = true

# `main`, on the rank axis. `-data` was the server's role leaking into the
# volume's name; a volume is project-local and is distinguished from a second
# one by rank rather than by what uses it. Renaming it does not disturb the
# mount: the on-host device is `/dev/disk/by-id/scsi-0HC_Volume_<id>`, keyed on
# the volume's id and not on its name — which is also why the on-host mount
# path at `/mnt/main` matching this name is a convenience rather than a
# derivation, and why the two may differ whenever a second stack in one
# project forces it.
volume_name = "main"
volume_size = 10
