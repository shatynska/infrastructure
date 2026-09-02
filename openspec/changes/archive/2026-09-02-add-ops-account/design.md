## Context

Confirmed against the repository before designing:

- `ansible/inventory/group_vars/prod.yml` sets `ansible_user: root`, and its
  own comment records why: the server was created with a single SSH key and no
  root password, so root is the only login the host has.
- `ansible/roles/deploy_user/tasks/main.yml` installs every `deploy` key with
  `key_options: 'restrict,command="/usr/local/bin/deploy-receive {{ item.name }}"'`.
  `restrict` disables pty allocation, so no `deploy` key can obtain a shell —
  by design (`add-per-app-deploy-keys`'s "A leaked key cannot be used to pivot
  into the host's network").
- `ansible/roles/hardening/tasks/main.yml` manages UFW and fail2ban only. It
  writes no `sshd_config`, so there is no `AllowUsers`/`AllowGroups` list a new
  account would have to be added to.
- UFW already allows 22 from `hardening_ssh_allowed_cidrs`
  (`176.104.184.0/24`, the operator's range) and from `100.64.0.0/10` (the
  tailnet). The operator's current workstation address falls inside that /24.
- `docker` is installed via the `docker` role (`geerlingguy.docker`), which
  creates the `docker` group.
- There is no CI workflow for Ansible; `.github/workflows/` covers Terraform
  (`apply.yml`, `drift.yml`, `pr-validation.yml`) and the platform Compose
  deploy only. Ansible converges by an operator running the playbook.

## Decisions

### A separate account, not another key on `deploy`

`authorized_keys` options are per-key, so an unrestricted interactive key
*could* technically be added to the existing `deploy` account. It is rejected
for two reasons, the second decisive:

1. The `deploy` account's guarantee — "a key here can only deliver one
   application's deploy" — stops being readable at a glance the moment one key
   on it is exempt. A reviewer would have to diff key options to know what the
   account can do.
2. `deploy` owns `/opt/<app>` for **every** application on the host, and each
   `/opt/<app>/.env` is written there by `deploy-receive`. An interactive shell
   on `deploy` would therefore be able to read every application's runtime
   secrets and rewrite any application's `docker-compose.yml` before its next
   deploy. That is a materially larger grant than "look at what commerce-ops is
   doing", and it would be granted silently, as a side effect of reusing a
   convenient account.

A separate unprivileged account owns nothing under `/opt` and cannot read a
`0600 deploy:deploy` file.

### Capability is `docker` group membership, and no `sudo` at all

Diagnosing this class of fault means `docker compose ps`, `docker compose
logs`, `docker exec` into a container, and `psql` inside the Postgres
container. All of those are Docker API operations; membership of the `docker`
group grants them and nothing else at the OS layer. The account gets **no**
`sudoers.d` file — not even a narrow one — so `apt`, `systemctl`, `ufw`,
`sshd_config` and every root-owned path stay out of reach through the ordinary
path.

**This is not a security boundary against the account's own holder, and must
not be documented as one.** Membership of the `docker` group is
root-equivalent by escalation: anyone who can talk to the Docker socket can
start a privileged container that bind-mounts `/` and write anywhere. Stating
this plainly is the point of writing it down — an account described as
"restricted" that is actually root-equivalent is worse than one described
accurately, because the next reader will trust the description.

What the account does buy, accurately stated:

- **Blast-radius containment against mistakes, not against intent.** A wrong
  command from this account fails on a permission error instead of succeeding;
  breaking out requires a deliberate, conspicuous act (launching a privileged
  container), not a typo.
- **Attribution.** Its logins are its own in `auth.log`/`last`, distinguishable
  from the operator's root sessions.
- **Independent revocation.** Removing its entry from `ops_user_accounts` and
  re-converging revokes it without touching the operator's own key, and without
  a key rotation on the deploy path.
- **Separation from deploy.** It cannot read another application's `.env` from
  the host filesystem, and cannot alter what a future deploy will run.

Note the honest limit on the third bullet: container environments are readable
through the Docker API, so an application's secrets are reachable by this
account by way of `docker inspect`/`docker exec` even though the host-side
`.env` is not. This account is a boundary on *host* administration, not on
*application* secrets.

### One account per operator identity, driven by a committed list

`ops_user_accounts` is a list of `{name, public_key, state}`, mirroring
`deploy_user`'s `deploy_apps` rather than inventing a second shape. One Unix
account per identity (rather than one shared `ops` account with several keys)
is what makes `auth.log` attribution and independent revocation real: with a
shared account, both operators appear as `ops` and revoking one means editing a
key list whose entries are indistinguishable in the logs they produce.

`state` is per-entry and defaults to `present`. It exists so revocation is a
converge, not a manual `userdel`: setting an entry to `absent` removes the
account and its home directory on the next run. A revocation path that only
works by hand is a revocation path that does not get used.

#### What revocation actually terminates

Revocation is the only mitigation this change offers for a grant it admits is
root-equivalent by escalation, so what it does and does not reach has to be
stated rather than assumed — a bare `state: absent` does not do what the
sentence above implies:

- `userdel` **refuses** an account that is currently logged in (exit 8), so a
  plain `state: absent` fails precisely in the case revocation exists for: a
  holder who is connected right now. Left there, the task errors and aborts
  `host-baseline.yml` for that host mid-run.
- Even forced, `userdel -f` removes the account without terminating an
  already-established SSH session. The holder keeps their shell, and their
  Docker socket access with it, until they disconnect.

So the role terminates first and removes second: `loginctl terminate-user`
plus `pkill -KILL -u <name>`, then `user: state=absent remove=true force=true`
(tasks.md 2.3). That makes "revoking an operator is one converge" true as
written, rather than true only against an idle account.

**Revoke by setting `state: absent` and leaving the entry in the list.
Deleting the entry is not revocation.** A list-driven role can only act on
entries it is given, so removing the `ops-claude` line outright produces a
converge that touches nothing and leaves the account, its home directory and
its authorized key exactly as they were — with no error to notice. This is the
more intuitive gesture and the one that silently fails, which is why it is
written down here and in the role's README rather than left to be discovered.
The entry stays, marked `absent`, until the operator is satisfied the account
is gone.

Two things it still does not reach, stated so nobody reads more into it:

- **Containers the account started are not stopped.** They run as root under
  `dockerd`, not as the account — and stopping them would mean an operator
  revocation taking down application containers, which is not what revocation
  should do. If the account is being revoked because its holder is *hostile*
  rather than merely finished, container state has to be audited separately;
  the escalation path this account carries means a hostile holder could have
  left root-owned changes behind that no user removal reverses.
- **Nothing about it is retroactive.** It ends access; it does not undo what
  was done with the access.

`authorized_key` is used with `exclusive: true` per account, so rotating a key
in the list actually removes the old one rather than accumulating both.

The public keys are committed in plaintext, exactly as `deploy_apps`'s already
are and for the same reason: a public key is not a credential. The private half
never enters this repository — it is generated on the operator's workstation
and stays there.

### Alternatives considered and deferred

- **Read-only Docker socket proxy** (e.g. a `docker-socket-proxy` container
  exposing only GET endpoints, with the account granted access to the proxy
  instead of the real socket). This would be a genuine boundary rather than an
  intent boundary, and it is the right answer if standing, unattended access is
  ever wanted. Rejected for now on two grounds: an unknown fault needs
  open-ended inspection (`docker exec`, `psql`) that a GET-only proxy forbids,
  and it would add a platform-stack service, putting `iac-platform-services` in
  scope for a change that is otherwise host configuration only. Worth
  revisiting if this account outlives the debugging it was created for.
- **Forced-command wrapper exposing a fixed command set** (the `deploy-receive`
  pattern, with `ps`/`logs` instead of a deploy). Strictly safer, and rejected
  for the same first reason: every new diagnostic question would need an
  infrastructure change before it could be asked.
- **Tailscale on the operator's workstation** as the access path. Not needed —
  the workstation's address is already inside the permitted operator CIDR — and
  orthogonal to this change: it would change *how the packets arrive*, not
  *what account they authenticate to*. If the operator's ISP address ever moves
  outside `176.104.184.0/24`, that is the fix, and it needs no change here.

## Risks

- **The escalation path is real.** Anyone holding this account's private key
  can become root on this host by deliberate means. The mitigation is not
  technical: it is that the key lives on the operator's own workstation, is
  used under the operator's supervision, and can be revoked in one converge
  (with the limits stated under "What revocation actually terminates").
  Recorded here rather than mitigated away.
- **The consumer-side permission rule must not remove that supervision.**
  tasks.md 6.2 has the operator add a Claude Code permission rule, because
  without one prod-targeted SSH is refused outright by the auto-mode
  classifier and the account would exist but be unusable by its intended
  holder. That rule is deliberately **ask-on-use and scoped to the
  `ops-claude` command shape**, not a blanket allow for prod SSH: the
  per-command prompt *is* the "used under the operator's supervision"
  mitigation named in the bullet above, so a blanket allow would delete the
  mitigation while appearing to be a convenience setting. If a blanket allow
  is ever wanted, that bullet has to be re-argued on attribution and
  revocability alone — supervision would no longer be available to it. The
  rule lives in the operator's own environment, not this repository; it is
  recorded here and in proposal.md's Impact because the change's stated risk
  posture depends on its shape.
- **Re-converging `host-baseline.yml` re-runs every role**, including
  `deploy_user`'s `docker_login` and `tailscale`'s idempotency check. Both are
  idempotent, but the run needs the Vault password (for `ghcr_pull_token`) and
  the tailnet auth key to be available, or those tasks fail. This is a property
  of the existing playbook, not of this change — it is called out so the
  rollout does not discover it.
- **fail2ban's sshd jail applies to the new account too.** Repeated failed key
  attempts from the workstation during setup can ban the operator's own
  address, locking out root as well. Verify the key works with a single
  deliberate attempt rather than a retry loop.

  Know the recovery route *before* needing it, because this change's own
  rejection of "Tailscale on the operator's workstation" leaves no second
  network path in: a ban on the operator's address closes SSH for root too,
  and root has no password (`group_vars/prod.yml`'s own comment records why),
  so the Hetzner console is not a login either. Recovery is a Hetzner-side
  root-password reset, then the console. Waiting out the jail's `bantime` is
  the other option. Neither is reachable from a shell on the host, which is
  the point of writing it down here.

- **A future sshd-hardening change can silently lock these accounts out.**
  This host's `sshd_config` carries no `AllowUsers`/`AllowGroups` today, which
  is why this change needs no sshd edit. Whoever adds one later must include
  every `ops_user_accounts` entry's account, or they stop being able to log in
  with no configuration in this role having changed. Recorded in the role's
  `README.md` as a standing obligation (tasks.md 2.4), where the next person
  editing SSH access is likelier to see it than in an archived change.
