## Why

A new application repository (`commerce-ops`, with roughly three more expected to follow) needs a way to deploy its own container to this host without SSH access to the whole box. The existing `deploy` account's privileged action is hardcoded to one fixed script operating on `/opt/platform` only, and its design deliberately rejected making that invocation reusable or argument-driven — it was never meant to serve a second application. Provisioning a full dedicated Unix account per application works but doesn't scale pleasantly to four (and growing) application repositories, each needing its own account, home directory, and sudoers rule.

This change also folds in two gaps surfaced during its own review, both host-side plumbing needed for a per-application deploy to actually complete rather than just reach the host:

1. **Registry pull authentication.** GHCR packages are private by default; nothing on this host currently authenticates to pull one.
2. **File transfer is incompatible with a per-key forced command.** A first draft of this change gave each key (including the existing platform key) a bare, single-invocation forced command. Review caught that this breaks `platform-deploy.yml`'s actual usage of its key: it doesn't send one command, it sends three in sequence (`scp` the compose file and `.env`, `ssh` a `chmod`, `ssh` the deploy trigger) — a forced command overrides every one of them, not just the last. The same defect was independently present in this change's own first draft of the *new* per-application mechanism, whose deploy job was likewise going to `scp` then separately trigger. Fixing this for real means changing how content reaches the host for every key, platform's included — which is why platform is now migrated onto the same generic mechanism rather than kept separate (see design.md for why keeping them separate turned out not to be viable).

## What Changes

- Add two scripts on the existing `deploy` account, working together within a single SSH session:
  - `/usr/local/bin/deploy-receive <app_name>` (owned `deploy:deploy`) — the SSH-layer forced command for every key. Reads an archive piped over stdin, extracts exactly `docker-compose.yml` and `.env` (nothing else, regardless of what else the archive contains) into `/opt/<app_name>`, sets restrictive permissions on `.env`, then invokes `sudo /usr/local/bin/app-deploy <app_name>` — all before the SSH session returns, so no second command ever needs to reach the host.
  - `/usr/local/bin/app-deploy <app_name>` (root:root) — unchanged in shape from the original design: `cd /opt/<app_name> && docker compose pull && docker compose up -d --wait`.
- Add one `sudoers.d` entry **per application** (platform included), each an exact, fully-qualified command line — no wildcard.
- Add one SSH keypair **per application** (platform's existing key gets a new restriction; every new application gets its own new keypair), each `authorized_keys` entry carrying `restrict,command="/usr/local/bin/deploy-receive <app_name>"` — `restrict` (in addition to `command=`) also disables port/agent/X11 forwarding and pty allocation, so a leaked key can't be used to tunnel into the host's network even though it already can't run anything but the one forced invocation.
- Provision `/opt/<app_name>` directories, owned by `deploy` — `/opt/platform` already exists; new ones (starting with `/opt/commerce-ops`) are added the same way.
- **Migrate `platform/`'s deploy mechanism onto this same generic mechanism.** `platform-compose-deploy` is retired; `platform-deploy.yml`'s deploy job changes from three sequential SSH operations (`scp`, `ssh chmod`, `ssh sudo`) to one: tar the compose file and `.env`, pipe them over a single SSH connection to the platform key's `deploy-receive` forced command. What `platform-compose-deploy` did (`docker compose pull && up -d --wait` in `/opt/platform`) is unchanged — only how content reaches the host and how the privileged action is invoked changes, and it changes identically to every other application. This is sequenced carefully (see design.md's Migration Plan and tasks.md's Rollout section): the workflow rewrite merges first (inert until a `platform/**` change triggers it), then the host-side key restriction and validation happen as one coordinated window, and only then is the old script actually deleted — the workflow-file change and the key restriction can't safely land at unrelated times.
- Authenticate the host to GHCR so `docker compose pull` (run with root privilege by `app-deploy`) can pull a private package: `docker login ghcr.io` run once against root's Docker credential store, using a read-only, `read:packages`-scoped GHCR token shared across applications.

## Capabilities

### New Capabilities
None.

### Modified Capabilities
- `iac-host-configuration`: removes the platform-specific "Restricted Deploy Account for Platform Stack Access" requirement (superseded — see Migration below), and adds two requirements: a generalized per-application forced-command deploy mechanism that platform itself now uses, and host-level GHCR pull authentication.

## Impact

- `ansible/roles/deploy_user/` (or a new role): adds tasks to install `deploy-receive` and `app-deploy`, render per-application `sudoers.d` entries (platform included), append per-application forced-command `authorized_keys` lines (replacing the platform key's current unrestricted entry), create per-application `/opt/<app_name>` directories, and authenticate root's Docker credential store to GHCR. The now-superseded `platform-compose-deploy` script and its sudoers entry are removed separately, in a later, validation-gated playbook run — not part of this same convergence (see tasks.md 5.6).
- `ansible/inventory/group_vars/prod.yml` (or Vault): the `deploy_user_public_key` variable is retired in favor of a unified `deploy_apps` list (name + public key per entry) that includes `platform` alongside every new application.
- **`/infrastructure`'s own `.github/workflows/platform-deploy.yml`**: the deploy job's file-delivery steps are rewritten from `scp` + two separate `ssh` commands to one `tar | ssh` pipe. This is the one place this change touches an existing, live, working pipeline — necessary because the review that shaped this change demonstrated the previous three-step approach cannot coexist with any per-key SSH-layer restriction. `platform/docker-compose.yml` itself is untouched.
- New per-application keypairs generated out-of-band (mirroring how the existing `deploy` keypair was generated) — the private half of each becomes a secret in that application's own GitHub repository, never committed here.
- A GHCR read-only (`read:packages`) token generated out-of-band, stored via Ansible Vault, used to `docker login` as root once during host configuration. `ansible/requirements.yml` gains a new pinned collection (`community.docker`, for the `docker_login` module) if hand-rolled tasks aren't used instead.
- No Terraform or cloud-firewall changes.
