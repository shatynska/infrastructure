# deploy_user

Provisions the restricted `deploy` system account that every application's GitHub Actions deploy job (`platform`'s included) authenticates as to deploy its own Compose stack over SSH -- one shared account, isolated per application, rather than a dedicated Unix account per application. See `add-per-app-deploy-keys`'s design.md for the full rationale, and `bootstrap-ansible-host-baseline`'s design.md for why this account exists at all.

## The unified shape

Every application in `deploy_apps` -- `platform` included -- gets:

- its own `/opt/<name>` directory, owned `deploy:deploy`, mode `0750`;
- its own SSH keypair, whose `authorized_keys` entry carries `restrict,command="/usr/local/bin/deploy-receive <name>"` -- the forced command binds the key to exactly one invocation, and `restrict` additionally disables port/agent/X11 forwarding and pty allocation, so a leaked key can't be used to tunnel into the host's network either; and
- its own `/etc/sudoers.d/app-deploy-<name>` rule, granting `deploy` passwordless `sudo` to run `/usr/local/bin/app-deploy <name>` with that exact, fully-qualified argument -- no wildcard.

A deploy reaches the host as one SSH session: the client pipes a tar archive containing `docker-compose.yml` and `.env` over stdin. `deploy-receive` (the forced command every key runs) extracts exactly those two members into `/opt/<name>` -- nothing else the archive might contain, regardless of its name -- sets restrictive permissions on the extracted `.env`, and triggers `sudo /usr/local/bin/app-deploy <name>`, which runs `docker compose pull && docker compose up -d --wait` in that directory and then reclaims the images that application's previous deploys left behind. No second command ever needs to reach the host over a given key.

Reclamation is scoped to the application's own image namespace -- `ghcr.io/<any owner>/<name>` -- and removes the tags there that the application's current Compose file does not reference. It runs after the containers are healthy, never forces a removal, is bounded in duration, reports what it did, and cannot fail a deploy that has already succeeded. See `openspec/specs/iac-host-configuration/spec.md`, "Superseded Application Images Are Reclaimed at Deploy Time".

Onboarding a new application requires only a new keypair, one `authorized_keys` line, one `sudoers.d` entry, and one `/opt/<name>` directory -- not a new Unix account, home directory, or sudoers structure.

One coupling to honour while doing so: an application's images must live at exactly `ghcr.io/<owner>/<name>` -- two path segments after the registry, the last of them equal to the name used here -- because that is how reclamation identifies the images it owns. Both an application deployed as `foo` whose images live at `ghcr.io/<owner>/bar`, and one publishing to a deeper path such as `ghcr.io/<owner>/foo/api`, have an empty namespace and reclaim nothing -- silently, and indistinguishably from an application that had nothing to reclaim.

## Key storage

This role installs only the **public** half of each application's keypair, via `deploy_apps`. Each keypair is generated out-of-band -- not by this playbook -- and its private half:

- Lives only in a GitHub Actions secret scoped to the `production` Environment in that application's own repository (never a plain repository-level secret), or
- Is stored in Ansible Vault if it needs to be re-applied by this role directly, encrypted at rest per this project's Secrets convention.

Either way, it is never committed in plaintext.

## GHCR pull authentication

`ghcr_pull_token` (a `read:packages`-scoped GitHub token) and `ghcr_pull_username` authenticate root's Docker credential store to GHCR, once, shared across every application -- not a credential per application, since it grants no capability beyond reading package contents. Without this, `app-deploy`'s `docker compose pull` cannot pull a private GHCR image.

### If a private image suddenly stops pulling, read this first

**The GHCR login is skipped when either half of the credential is missing, and the run still reports success.** That is deliberate (`repair-ansible-test-harness`): a host that pulls no private image should not need a GHCR credential, and requiring one made the whole Molecule suite unrunnable without a live token.

The cost is that a credential problem no longer fails the converge. It surfaces later, at the next `docker compose pull` during a deploy -- in a different pipeline, further from the change that caused it. Two ways to land there:

- the token was **rotated or revoked** since it was encrypted into Vault; or
- the variable is **misnamed, or its vars file did not load**, on a host that genuinely does need the credential.

The second is the likelier and the quieter of the two. To tell them apart, re-run the playbook and look for the task *"Report that GHCR authentication was skipped for want of a credential"*. If it fired, the host never authenticated at all and the problem is the variables, not the token. If it did not fire, the login ran, so the credential reached the registry -- and a credential that is supplied and *rejected* still fails the converge loudly, exactly as before. That distinction is deliberate: the guard tolerates an absent credential, never a refused one.

## What this account can do

Its only privileged capability, per application, is `sudo`-triggering one fixed, fully-qualified invocation of `/usr/local/bin/app-deploy <name>` -- no `docker`-group membership, no raw `docker`/`docker compose` access, and no application's key can trigger another application's deploy. See `add-per-app-deploy-keys`'s design.md for the accepted content-layer trust boundary this restriction does and doesn't cover.

## The read-only probe

An application may also be given a **second** key, bound to `/usr/local/bin/deploy-probe <name>`, which answers one token about its own database in the shared instance and writes nothing anywhere. It is a second key rather than a second command because an `authorized_keys` entry carries one `command=`. The field is `probe_public_key` and it is optional: an entry omitting it gets its deploy entry as before, no probe entry, no probe `sudoers` rule, and no failure.

The split mirrors the deploy path exactly. `deploy-probe` is `deploy`-owned, holds no privilege, bounds what it reads and forwards it; `/usr/local/bin/app-probe` is root-owned and reached only through `/etc/sudoers.d/app-probe-<name>`, fully qualified to one application. **Every answer is decided in `app-probe`**, the window included, so that one place decides and a bug in the unprivileged half cannot suppress an answer.

The tokens, in precedence order, are `window-open`, `unreachable`, `absent`, `credential-refused`, `empty` and `populated`. The probe exits zero when and only when it emits one; anything else exits non-zero with a diagnostic and no token. `openspec/specs/iac-host-configuration/spec.md`, *An Application Can Probe Its Own Database Through a Read-Only Forced Command*, is the contract, and `docs/onboard-an-application.md` §4 is what a consuming repository reads.

**`app-probe` names `platform-postgres-1`, and reads the image its client runs from that container rather than carrying a copy of the pin.** Both are deliberate. The probe's subject *is* the shared instance, so taking the container name as input would put it back on the client side, which the two-layer name pinning exists to prevent; and `platform/docker-compose.yml` holds the pin with Dependabot proposing the next one, so a second copy here would drift silently and be discovered by a probe failing after an upgrade. Reading it from the container also keeps the client's `psql` matched to the server. It does assume that image carries `bash`, which the Debian-based official image does and an Alpine variant would not.

## The maintenance window declaration

    /var/lib/platform-maintenance/shared-postgres-window

Raise it with `touch` on that path, withdraw it with `rm`. While it exists, every probe on this host answers `window-open` whatever stands beneath it.

**No `sudo` is needed for either**, and none is granted: this role creates `/var/lib/platform-maintenance/` root-owned, group `docker`, mode `0775`, and `docker` is the group an operator account already holds — `ops_user` writes no `sudoers.d` file of any kind and that omission is its requirement. Granting that group write access adds no capability, since that role's own README records `docker` membership as root-equivalent by escalation; it makes an already-available act convenient rather than newly possible. The directory is world-readable so that nothing about who may *read* the declaration depends on group membership.

It sits outside the volume it announces, which is discarded during the window, and outside `/opt/<app>`, which an operator cannot read.

**A declaration left raised fails safe**: applications keep being told a window is open and keep not delivering, which costs a delayed deploy rather than a delivery into a destroyed instance. `platform/README.md`'s *Upgrading the PostgreSQL major version* raises it at step 1 and withdraws it at the end of step 4 — not after step 5, whose own redeploys go through the probe and would otherwise be blocked by the window they are ending.

## Variables

| Variable | Default | Description |
|---|---|---|
| `deploy_apps` | *(required, no default)* | List of `{name, public_key}`, each entry optionally carrying `probe_public_key` -- one entry per application allowed to deploy to this host, `platform` included. |
| `ghcr_pull_token` | *(required, no default)* | A `read:packages`-scoped GHCR token, shared across every application. |
| `ghcr_pull_username` | *(required, no default)* | The username paired with `ghcr_pull_token` for `docker login ghcr.io`. |
