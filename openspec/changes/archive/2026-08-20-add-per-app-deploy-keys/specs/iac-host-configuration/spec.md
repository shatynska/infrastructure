## ADDED Requirements

### Requirement: Restricted Deploy Account Supports Per-Application Forced-Command Deploys
Ansible SHALL extend the existing `deploy` account to support deploying multiple applications — including `platform` itself, which uses this same mechanism rather than a separate one — without provisioning a new Unix account per application. For each application, Ansible SHALL provision: an `/opt/<app_name>` directory owned by `deploy`; a `sudoers.d` entry granting `deploy` passwordless `sudo` to run `/usr/local/bin/app-deploy <app_name>` with that exact, fully-qualified argument (no wildcard); and an `authorized_keys` entry for that application's own SSH keypair, carrying both a `command=` forced command binding it to exactly one invocation (`/usr/local/bin/deploy-receive <app_name>`) and the `restrict` option, so that no SSH channel feature — port forwarding, agent forwarding, X11 forwarding, or pty allocation — is available to that key beyond the one forced invocation.

`deploy-receive` SHALL read an archive delivered over the SSH session's standard input, extract only that application's `docker-compose.yml` and `.env` members into `/opt/<app_name>` (any other archive member SHALL NOT be extracted, regardless of its name or path), set restrictive permissions on the extracted `.env`, and then invoke `sudo /usr/local/bin/app-deploy <app_name>` — all within that one SSH session, so that delivering content and triggering the deploy never requires more than one command to reach the host over a given key.

The set of deployable application names SHALL be enumerated in version control (as `sudoers` entries and `authorized_keys` forced commands), not accepted as free-form input at either the SSH or the `sudo` layer — an application name reaches the privileged script only via a value fixed ahead of time by which key connected and which `sudoers` rule matches, never as data supplied by the connecting client at connection time.

#### Scenario: A single SSH session delivers content and triggers deploy
- **WHEN** an application's key connects and pipes an archive over standard input
- **THEN** `deploy-receive` SHALL extract that application's `docker-compose.yml` and `.env` into its own `/opt/<app_name>` directory and trigger its deploy within that same session, without requiring a second command to be sent over the connection

#### Scenario: Archive members outside the expected set are ignored
- **WHEN** a delivered archive contains a member other than `docker-compose.yml` or `.env`
- **THEN** `deploy-receive` SHALL NOT extract that member, regardless of its name or path

#### Scenario: An application's key can only ever deploy that application
- **WHEN** an application's SSH key connects to the `deploy` account
- **THEN** the only action available to that session SHALL be delivering and deploying that application's own content via `deploy-receive <that application's fixed name>`, and the session SHALL NOT be able to supply a different application name, send a second command, or trigger a deploy for any other application

#### Scenario: A leaked key cannot be used to pivot into the host's network
- **WHEN** an application's SSH key is used to open a port-forwarding, agent-forwarding, X11-forwarding, or pty-allocating channel, rather than the one forced command
- **THEN** the connection SHALL be refused, independent of and in addition to the forced-command restriction on what that key can execute

#### Scenario: An unenumerated application name is rejected
- **WHEN** a `sudo` invocation of `/usr/local/bin/app-deploy` is attempted with an application name that has no corresponding `sudoers.d` entry
- **THEN** `sudo` SHALL refuse to run it, independent of any validation performed inside either script

#### Scenario: New applications are onboarded without a new account
- **WHEN** a new application needs to deploy to this host
- **THEN** onboarding it SHALL require only a new keypair, one `authorized_keys` forced-command line, one `sudoers.d` entry, and one `/opt/<app_name>` directory — not a new Unix account, home directory ownership model, or sudoers structure

#### Scenario: Platform deploys through the same mechanism as every other application
- **WHEN** the platform key connects
- **THEN** it SHALL trigger `deploy-receive platform` exactly as any other application's key triggers its own deploy, with no separate platform-specific script or `sudoers` rule remaining on the host

### Requirement: Host Authenticates to GHCR for Application Image Pulls
Ansible SHALL configure root's Docker credential store on the host with a read-only (`read:packages`-scoped) GHCR token, so that `docker compose pull` invocations run by `/usr/local/bin/app-deploy` succeed against a private GHCR package. This credential SHALL be shared across every application on the host rather than provisioned per application, since it grants no capability beyond reading package contents.

#### Scenario: A private GHCR package can be pulled during deploy
- **WHEN** `docker compose pull` runs as part of an application's deploy, referencing a private image hosted on GHCR
- **THEN** the pull SHALL succeed using the host's configured GHCR credential, without any application-specific pull credential being provisioned

#### Scenario: GHCR token is never committed
- **WHEN** the GHCR token is generated or rotated
- **THEN** it SHALL be stored outside version control (Ansible Vault) and SHALL NOT appear in plaintext anywhere in the repository

## REMOVED Requirements

### Requirement: Restricted Deploy Account for Platform Stack Access
**Reason**: Superseded by the generalized "Restricted Deploy Account Supports Per-Application Forced-Command Deploys" requirement above, which platform now uses identically to every other application. Maintaining a separately named, platform-specific script and requirement became untenable once review established that the multi-step `scp`-based transfer this requirement assumed (`scp`, then a separate `chmod`, then a separate `sudo` trigger — three commands over one key) is incompatible with any per-key SSH-layer forced-command restriction, which by definition permits only one. The generalized single-session mechanism replaces it for every application, platform included.

**Migration**: `platform-compose-deploy` and its dedicated `sudoers` entry are removed from the host. `platform-deploy.yml`'s deploy job is rewritten to tar `docker-compose.yml` and `.env` and pipe them over one SSH connection to the platform key's new `deploy-receive` forced command, exactly as every other application's deploy job does. `platform/docker-compose.yml` itself, and what `docker compose pull && up -d --wait` does once triggered, are unchanged — only how content reaches the host and how the privileged action is invoked changes, uniformly across every application.
