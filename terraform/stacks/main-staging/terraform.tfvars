# Non-secret configuration for the main-staging stack. Committed per the
# Version Control Excludes State and Secrets requirement — CI needs these
# values present in a clean checkout.

# THE SERVER TAKES ITS STACK'S NAME, and that it differs from the production
# stack's is load-bearing rather than cosmetic — but it is no longer something
# this file has to arrange. The server's name is the stack's, every stack's
# name is distinct, and the distinctness follows from the scheme rather than
# from a choice made here.
#
# Why it has to be distinct at all: the hcloud inventory plugin takes each
# host's `inventory_hostname` from the server name, so two hosts sharing one
# would merge under any inventory reading both projects, and would share a
# single `<inventory_hostname>-prune-host-images` heartbeat check -- where the
# live host's weekly success keeps the check green while the other's timer is
# dead. docs/bootstrap-a-new-host.md, Appendix C, names that masking failure.
name = "main-staging"

# Roughly half prod's `cx33` (4 vCPU / 8 GB). Read off the Hetzner console for
# staging's own project by the operator (task 1.3) rather than guessed here: no
# credential in this repository or in a fresh working tree can confirm which
# 2-vCPU type name is current, and a wrong one is discovered at apply against a
# project that already exists.
server_type = "cx23"

image    = "ubuntu-26.04"
location = "hel1"

ssh_public_key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIMeSWD47lN9AUVvOF2/7llxkBY0WWDgmAA1VwgIdhQsW"

# The same operator ISP range prod allows: the cloud firewall is no wider for
# staging than for prod.
ssh_allowed_cidrs = ["176.104.184.0/24"]

# Open to the internet, as prod's is. Traefik is the only listener on 80/443,
# and both have to be public rather than allowlisted: Let's Encrypt's
# TLS-ALPN-01 challenge connects inbound to 443 from addresses it does not
# publish, and the applications staging serves take webhooks from sources
# with no stable allowlist either. With no application router, Traefik
# answers 301 on 80 and 404 behind its default certificate on 443.
#
# Mirrored by hardening_web_allowed_cidrs in group_vars/staging.yml.
web_allowed_cidrs = ["0.0.0.0/0"]

server_enabled = false

volume_enabled = true

# `main`, on the rank axis, and deliberately the same name the production
# stack's volume carries. Volume names are unique per Hetzner project, not
# globally, and staging has a project of its own — so the name is free, and
# using the same one in both keeps the on-host mount path identical across
# stacks, which is what lets platform/docker-compose.yml stay unparameterised.
#
# The mount path is not derived from the volume's name, though the two now
# agree at `/mnt/main`: the on-host device is
# `/dev/disk/by-id/scsi-0HC_Volume_<id>`, keyed on the volume's id rather than
# its name, so a volume rename costs no migration and no remount.
volume_name = "main"
volume_size = 10
