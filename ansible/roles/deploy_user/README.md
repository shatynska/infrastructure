# deploy_user

Provisions the restricted `deploy` system account that every application's
GitHub Actions deploy job (`platform`'s included) authenticates as to
deploy its own Compose stack over SSH -- one shared account, isolated per
application, rather than a dedicated Unix account per application. See
`openspec/changes/add-per-app-deploy-keys/design.md` for the full
rationale, and `openspec/changes/bootstrap-ansible-host-baseline/design.md`
for why this account exists at all.

## The unified shape

Every application in `deploy_apps` -- `platform` included -- gets:

- its own `/opt/<name>` directory, owned `deploy:deploy`, mode `0750`;
- its own SSH keypair, whose `authorized_keys` entry carries
  `restrict,command="/usr/local/bin/deploy-receive <name>"` -- the forced
  command binds the key to exactly one invocation, and `restrict`
  additionally disables port/agent/X11 forwarding and pty allocation, so a
  leaked key can't be used to tunnel into the host's network either;
  and
- its own `/etc/sudoers.d/app-deploy-<name>` rule, granting `deploy`
  passwordless `sudo` to run `/usr/local/bin/app-deploy <name>` with that
  exact, fully-qualified argument -- no wildcard.

A deploy reaches the host as one SSH session: the client pipes a tar
archive containing `docker-compose.yml` and `.env` over stdin.
`deploy-receive` (the forced command every key runs) extracts exactly
those two members into `/opt/<name>` -- nothing else the archive might
contain, regardless of its name -- sets restrictive permissions on the
extracted `.env`, and triggers `sudo /usr/local/bin/app-deploy <name>`,
which runs `docker compose pull && docker compose up -d --wait` in that
directory. No second command ever needs to reach the host over a given
key.

Onboarding a new application requires only a new keypair, one
`authorized_keys` line, one `sudoers.d` entry, and one `/opt/<name>`
directory -- not a new Unix account, home directory, or sudoers structure.

## Key storage

This role installs only the **public** half of each application's
keypair, via `deploy_apps`. Each keypair is generated out-of-band -- not
by this playbook -- and its private half:

- Lives only in a GitHub Actions secret scoped to the `production`
  Environment in that application's own repository (never a plain
  repository-level secret), or
- Is stored in Ansible Vault if it needs to be re-applied by this role
  directly, encrypted at rest per this project's Secrets convention.

Either way, it is never committed in plaintext.

## GHCR pull authentication

`ghcr_pull_token` (a `read:packages`-scoped GitHub token) and
`ghcr_pull_username` authenticate root's Docker credential store to GHCR,
once, shared across every application -- not a credential per application,
since it grants no capability beyond reading package contents. Without
this, `app-deploy`'s `docker compose pull` cannot pull a private GHCR
image.

### If a private image suddenly stops pulling, read this first

**The GHCR login is skipped when either half of the credential is missing,
and the run still reports success.** That is deliberate
(`openspec/changes/repair-ansible-test-harness`): a host that pulls no
private image should not need a GHCR credential, and requiring one made the
whole Molecule suite unrunnable without a live token.

The cost is that a credential problem no longer fails the converge. It
surfaces later, at the next `docker compose pull` during a deploy -- in a
different pipeline, further from the change that caused it. Two ways to land
there:

- the token was **rotated or revoked** since it was encrypted into Vault; or
- the variable is **misnamed, or its vars file did not load**, on a host that
  genuinely does need the credential.

The second is the likelier and the quieter of the two. To tell them apart,
re-run the playbook and look for the task *"Report that GHCR authentication
was skipped for want of a credential"*. If it fired, the host never
authenticated at all and the problem is the variables, not the token. If it
did not fire, the login ran, so the credential reached the registry -- and a
credential that is supplied and *rejected* still fails the converge loudly,
exactly as before. That distinction is deliberate: the guard tolerates an
absent credential, never a refused one.

## What this account can do

Its only privileged capability, per application, is `sudo`-triggering one
fixed, fully-qualified invocation of `/usr/local/bin/app-deploy <name>` --
no `docker`-group membership, no raw `docker`/`docker compose` access, and
no application's key can trigger another application's deploy. See
`openspec/changes/add-per-app-deploy-keys/design.md` for the accepted
content-layer trust boundary this restriction does and doesn't cover.

## Variables

| Variable | Default | Description |
|---|---|---|
| `deploy_apps` | *(required, no default)* | List of `{name, public_key}` -- one entry per application allowed to deploy to this host, `platform` included. |
| `ghcr_pull_token` | *(required, no default)* | A `read:packages`-scoped GHCR token, shared across every application. |
| `ghcr_pull_username` | *(required, no default)* | The username paired with `ghcr_pull_token` for `docker login ghcr.io`. |
