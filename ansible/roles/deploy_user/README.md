# deploy_user

Provisions the restricted `deploy` system account that
`deploy-platform-compose-stack`'s GitHub Actions workflow authenticates as
to deploy `platform/`'s Compose stack over SSH. See
`openspec/changes/bootstrap-ansible-host-baseline/design.md` for the full
rationale behind this account's shape.

## Key storage

This role installs only the **public** half of the deploy keypair (via
`deploy_user_public_key`). The keypair itself is generated out-of-band —
not by this playbook — and its private half:

- Lives only in a GitHub Actions secret scoped to the `production`
  Environment (never a plain repository-level secret — see this project's
  `bootstrap-ansible-host-baseline` change's tasks.md 3.2 for why that
  scoping is load-bearing for an accepted trust boundary), or
- Is stored in Ansible Vault if it needs to be re-applied by this role
  directly, encrypted at rest per this project's Secrets convention.

Either way, it is never committed in plaintext.

## What this account can do

Its only privileged capability is `sudo`-triggering one fixed,
argument-free script, `/usr/local/bin/platform-compose-deploy` — no
`docker`-group membership, no raw `docker`/`docker compose` access. See
the parent change's design.md for the accepted content-layer trust
boundary this restriction does and doesn't cover.

## Variables

| Variable | Default | Description |
|---|---|---|
| `deploy_user_public_key` | *(required, no default)* | The deploy account's authorized SSH public key. |
