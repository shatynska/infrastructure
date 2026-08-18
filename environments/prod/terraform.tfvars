# Non-secret prod configuration. Committed per the Version Control
# Excludes State and Secrets requirement — CI needs these values present
# in a clean checkout.

name        = "prod"
server_type = "cx22"
image       = "ubuntu-24.04"
location    = "fsn1"

# ssh_public_key and ssh_allowed_cidrs are intentionally NOT set here yet.
# They depend on decisions/actions blocked on tasks 1.6 (SSH source CIDRs
# — do not default to 0.0.0.0/0) and 1.7 (SSH key pair). Add both once
# those are resolved; until then, plan/apply against this environment
# will fail with a "no value" error for these two variables, which is
# the intended fail-safe rather than a guessed placeholder.
