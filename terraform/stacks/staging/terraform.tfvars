# Non-secret staging configuration. Committed per the Version Control
# Excludes State and Secrets requirement — CI needs these values present
# in a clean checkout.

# NOT prod's "main-server", and the difference is load-bearing rather than
# cosmetic. modules/server sets the SERVER's name from this value directly
# (only the firewall carries the "<environment>-" prefix), and the hcloud
# inventory plugin takes each host's `inventory_hostname` from the server name.
# Two hosts sharing one would merge under any inventory that reads both
# projects, and would share a single `<inventory_hostname>-prune-host-images`
# heartbeat check -- where the live host's weekly success keeps the check green
# while the other's timer is dead. docs/bootstrap-a-new-host.md, Appendix C,
# names that masking failure; this is the first stack able to cause it.
name = "staging-server"

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

# Empty, and empty on purpose: staging runs nothing yet. This creates no web
# rule at all, rather than opening 80/443 to the internet on a host with
# nothing behind them. The change that deploys the platform stack to staging
# opens them deliberately.
web_allowed_cidrs = []

server_enabled = true

volume_enabled = true

# Deliberately the same name prod's volume carries. Volume names are unique
# per Hetzner project, not globally, and staging has a project of its own —
# so the name is free, and reusing it keeps the on-host mount path identical
# across stacks, which is what lets platform/docker-compose.yml keep
# its hardcoded /mnt/main-data/prometheus and /mnt/main-data/grafana.
volume_name = "main-data"
volume_size = 10
