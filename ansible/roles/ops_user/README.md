# ops_user

Provisions unprivileged, **interactive** operator accounts on the prod host
— one Unix account per operator identity, each with its own SSH key, a
normal shell, and membership of the `docker` group. Implements
`iac-host-configuration`'s "Unprivileged Operator Accounts Support
Interactive Host Inspection" requirement. See
`openspec/changes/add-ops-account/design.md` for the full rationale.

It exists because this host previously had exactly one interactive login —
`root`. The `deploy` account is deliberately shell-less (every key on it
carries `restrict,command=...`), so diagnosing a misbehaving application
meant handing out root.

## What this account actually grants — read this before trusting it

**`docker` group membership is root-equivalent by escalation.** Anyone who
can talk to the Docker socket can start a privileged container that
bind-mounts `/` and write anywhere on the host. This account is therefore
**not** a confidentiality or integrity boundary against its own key holder,
and must never be documented or relied upon as one. An account described as
"restricted" that is actually root-equivalent is worse than one described
accurately, because the next reader will trust the description.

What it does buy, accurately stated:

- **Blast-radius containment against mistakes, not against intent.** A wrong
  command fails on a permission error instead of succeeding; breaking out
  requires a deliberate, conspicuous act, not a typo.
- **Attribution.** Each identity's logins are its own in `auth.log`/`last`,
  distinguishable from the operator's root sessions.
- **Independent revocation.** One converge, without touching the operator's
  root key or rotating anything on the deploy path.
- **Separation from `deploy`.** It owns nothing under `/opt`, so it cannot
  read another application's deployed `.env` or rewrite the
  `docker-compose.yml` a future deploy will run.

Honest limit on that last point: container environments are readable
through the Docker API, so an application's secrets remain reachable by way
of `docker inspect`/`docker exec`. This is a boundary on *host*
administration, not on *application* secrets.

## This role writes no `sudoers` file, and never should

There is no `sudoers.d` task here, and its absence is the requirement — not
an omission waiting to be filled in. The account gets **no** `sudo` at all,
not even a narrow rule, so `apt`, `systemctl`, `ufw`, `sshd_config` and
every root-owned path stay out of reach through the ordinary path. If a
future change appears to need one, that is a change to the requirement, not
a detail to add here.

## Revocation

Set the entry's `state` to `absent` and **leave the entry in the list**:

```yaml
ops_user_accounts:
  - name: ops-claude
    public_key: "ssh-ed25519 AAAA... ops-claude"
    state: absent
```

**Deleting the entry outright is not revocation.** This role can only act on
entries it is given, so removing the line produces a converge that touches
nothing and leaves the account, its home directory and its authorized key
exactly as they were — with no error to notice. Keep the entry, marked
`absent`, until you have confirmed the account is gone.

Revocation terminates the account's login sessions (`loginctl
terminate-user`) and kills its remaining processes before removing it. That
ordering is load-bearing: `userdel` refuses an account that is currently
logged in, and even forced it would leave an established session alive with
its Docker socket access intact.

Two things revocation does **not** reach:

- **Containers the account started are not stopped.** They run as root under
  `dockerd`, not as the account, and stopping them would mean revoking an
  operator took down application containers. If an account is being revoked
  because its holder is hostile rather than merely finished, container and
  host state must be audited separately — the escalation path above means a
  hostile holder could have left root-owned changes behind that no account
  removal reverses.
- **Nothing about it is retroactive.** It ends access; it does not undo what
  was done with the access.

## Standing obligation: sshd access lists

This host's `sshd_config` carries no `AllowUsers`/`AllowGroups` directive
today (the `hardening` role manages UFW and fail2ban only), which is why
these accounts are reachable without any sshd change. **If such a directive
is ever added, every `ops_user_accounts` account must be included in it** —
otherwise these accounts are silently locked out with nothing in this role
having changed.

## Key storage

This role installs only the **public** half of each operator's keypair, via
`ops_user_accounts`. Each keypair is generated out-of-band on the operator's
own workstation — not by this playbook — and the private half never enters
this repository. Public keys are committed in plaintext, exactly as
`deploy_apps`'s already are and for the same reason: a public key is not a
credential.

`ansible.posix.authorized_key` is used with `exclusive: true` per account,
so replacing an entry's `public_key` rotates the key rather than leaving
both the old and the new one installed.

## Variables

| Variable | Default | Description |
|---|---|---|
| `ops_user_accounts` | `[]` | List of `{name, public_key, state}` — one entry per operator identity. `state` is per-entry and defaults to `present`; `absent` revokes. Empty means no operator accounts are provisioned. |
