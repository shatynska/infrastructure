## Context

`ansible/requirements.yml` already pins `geerlingguy.docker` (8.0.0) and the
`hetzner.hcloud` collection (7.0.0); `ansible/inventory/hcloud.yml` already
resolves the `prod` group dynamically. None of that has a playbook driving
it yet — `ansible/playbooks/` and `ansible/roles/` are empty. See
proposal.md for why this change exists now: `platform/`'s Compose stack
(Traefik + Postgres, proposed separately) needs a deploy account to exist
before its GitHub Actions workflow can be built.

**Correction (caught only at implementation time):** earlier drafts of
this design, and of the sibling `deploy-platform-compose-stack` change,
stated `web_allowed_cidrs` was unset in
`terraform/environments/prod/terraform.tfvars`, based on a grep that
never actually searched for that string. It is in fact already set to
`["0.0.0.0/0"]` — the cloud firewall already opens 80/443 publicly, and
no separate Terraform change is needed for that. This changes nothing
about the mechanism decisions elsewhere in this document (the deploy
account, the wrapper script, the test framework) — only the Goals/
Non-Goals framing below and the concrete UFW values this change's
group_vars should carry, both corrected accordingly.

## Goals / Non-Goals

**Goals:**
- A working playbook that installs Docker, hardens the host (UFW, fail2ban),
  and provisions the restricted `deploy` account, runnable idempotently
  against the `prod` inventory group.
- Firewall rules (UFW) that mirror exactly what `terraform/modules/server`'s
  Hetzner cloud firewall allows — no port open at one layer and assumed
  closed at the other, per the existing Host-Level Security Owned by
  Ansible, Cloud Firewall Owned by Terraform requirement.

**Non-Goals:**
- Building the GitHub Actions workflow that will use the `deploy` account —
  that is a separate, not-yet-proposed change.
- Deciding or implementing anything under `platform/` (Compose file, Traefik
  config, Postgres config).
- Changing the cloud firewall layer itself — `web_allowed_cidrs` in
  `terraform/environments/prod/terraform.tfvars` is already set to
  `["0.0.0.0/0"]` (corrected after this design initially, incorrectly,
  assumed it was unset — see Context below), so no Terraform change is
  needed or in scope here; this change's UFW rules mirror that existing
  state rather than waiting on one.

## Decisions

**Test framework: Molecule.** This repo's AGENTS.md establishes a test
convention for Terraform (`terraform test` / `*.tftest.hcl`) but is silent
on Ansible — no role has existed to test until now. Molecule is adopted as
this project's Ansible test framework, one scenario directory per role
(`ansible/roles/<role>/molecule/default/{molecule.yml,converge.yml,
verify.yml}`), run via `molecule test` from within each role's directory;
test-path glob `ansible/roles/*/molecule/**/*.yml`. Chosen over
lightweight `ansible.builtin.assert` playbooks because it exercises a real
converge-then-verify cycle (closer to what `terraform test` gives
Terraform) rather than just asserting on rendered variables, and it's the
standard tool referenced by this project's own `ansible` skill guidance.
Molecule and its driver are new external dependencies for this repo and
SHALL be pinned to exact versions per the existing "any external role or
collection... pinned to an exact version" convention, even though they
arrive via pip rather than Galaxy. This choice becomes this project's
Ansible test convention going forward, the same way `terraform test` did
for Terraform once `terraform/modules/` grew past its first module.

**Role structure**: one playbook (`ansible/playbooks/host-baseline.yml`)
composing three roles: `docker` (wraps the pinned `geerlingguy.docker`
role), `hardening` (UFW + fail2ban, hand-written — no external role pinned
for this, since the ruleset is small and project-specific), and `deploy_user`
(the restricted account). Kept as separate roles rather than one monolithic
playbook so each can be run/tested independently and matches the existing
convention of one concern per unit.

**Deploy account shape**: a system user (`deploy`, no password, key-only
auth) whose home directory *is* `/opt/platform` (mode `0750`, owned
`deploy:deploy`) — this is the canonical fixed path both this change and
its follow-up (`deploy-platform-compose-stack`) reference; nothing beyond
this design decides it independently. Its only privileged capability is
triggering a fixed, root-owned, **argument-free** wrapper script via
`sudo`:

```
#!/bin/bash
# /usr/local/bin/platform-compose-deploy — root:root, mode 0755
set -euo pipefail
cd /opt/platform
docker compose pull
docker compose up -d --wait
```

paired with a `sudoers.d` drop-in granting exactly:
`deploy ALL=(root) NOPASSWD: /usr/local/bin/platform-compose-deploy` — no
wildcard, no arguments accepted, so nothing can be appended to or
substituted in the invocation. `docker compose up -d --wait` blocks until
every service reports running/healthy and exits non-zero otherwise, which
doubles as the post-deploy health check the follow-up change needs — no
separate unprivileged `docker compose ps` step is required (or possible,
since `deploy` has no other way to reach the Docker socket).

Rejected: adding `deploy` to the `docker` group (root-equivalent — a
member can bind-mount the host root filesystem into a container). Also
rejected, on review, a `sudoers` rule that forwarded raw `docker compose`
arguments (e.g. `docker compose -f /opt/platform/docker-compose.yml *`):
`docker compose run`/`exec` accept `-v`, `--privileged`, and `--user root`
on that same invocation line, which is exactly as root-equivalent as
`docker`-group membership — the escape just moved to a different door. A
script with no argument passthrough at all closes that specific door:
there is nothing an attacker holding the `deploy` key can append to, or
substitute into, the one permitted invocation.

**What this does and doesn't close.** The wrapper eliminates
*invocation-layer* escalation — no argument injection, no alternate
command. It does not, and structurally cannot, eliminate
*content-layer* escalation: `deploy` owns `/opt/platform`, the directory
the wrapper's `docker compose` auto-discovers its file from, because
owning that directory is how a deployment mechanism gets new Compose
content onto the host at all. A `deploy`-key holder can write a
`docker-compose.yml` with `privileged: true` and a root bind mount, then
trigger the one permitted command, and root will apply it — full host
compromise, reached through content rather than arguments. This was
raised on review and is addressed below as an accepted trust boundary
rather than an implementation gap to close, since closing it (a
root-owned staging/promotion step, or a Compose-content denylist) would
add a second privileged actor or an inherently-incomplete validation
layer to guard against a threat this design already contains at a
different layer. See Risks / Trade-offs.

## Risks / Trade-offs

- [UFW rules drift from the cloud firewall as either side changes] →
  Mitigated by writing UFW's allowed ports from the same values the cloud
  firewall already carries (22 from the configured SSH CIDR; 80/443 from
  `0.0.0.0/0`, since `web_allowed_cidrs` is already set), and calling this
  out explicitly in tasks.md so a future firewall change on either side
  prompts a look at the other.
- [Restricted account is provisioned but its restriction mechanism is picked
  without seeing the actual GitHub Actions workflow that will use it] →
  Mitigated by keeping the choice reversible: switching to a forced-command
  SSH key later only touches this account's `authorized_keys` entry and
  `sudoers.d` drop-in, not anything in `platform/`. The wrapper script's
  fixed, argument-free contract also means the follow-up change has nothing
  to get wrong on its end — it either calls the one permitted command or it
  doesn't.
- [Non-interactive `sudo` over CI-driven SSH may require `requiretty` to be
  unset for `deploy`, which isn't stated anywhere by default] → The
  `deploy_user` role SHALL explicitly ensure `deploy` is exempted from any
  `requiretty` default (or that none is set), and tasks.md includes a
  verification step invoking the permitted command the same way CI will
  (`ssh deploy@host sudo /usr/local/bin/platform-compose-deploy`, no PTY).
- [**Accepted risk**: `deploy` can escalate to root by writing a hostile
  `docker-compose.yml` into the directory it owns, then triggering the one
  permitted command — the invocation is restricted, but the content it
  operates on is not] → Not mitigated at this account's level; accepted
  because the actual containment for this account's key sits one layer up,
  in the deployment mechanism that holds it: `deploy-platform-compose-stack`
  stores this key only in a `production`-scoped GitHub Environment secret,
  unreadable until that Environment's required reviewer approves — and (on
  a first pass through review, this design incorrectly assumed a PR-time
  review was what made that approval meaningful; that repo's branch
  protection requires only a passing status check, not an approving
  review, so that assumption didn't hold) `deploy-platform-compose-stack`
  now posts the exact diff being deployed to the run's job summary via a
  credential-less job that runs *before* the approval gate is presented,
  so the actual guarantee is "the Environment's required reviewer saw this
  exact diff immediately before approving," independent of whatever
  review, if any, happened on the originating pull request (see that
  change's "Reviewer Sees the Exact Diff Before Approving" requirement). A
  `deploy`-key holder with no accompanying access to get a Compose change
  approved through that gate is the threat this restriction was built for,
  and against that threat the invocation-layer restriction still holds:
  they can run only the one fixed action against whatever content already
  sits in `/opt/platform`, not an arbitrary command. A `deploy`-key holder
  who can *also* get a Compose change approved through the gate already
  has the access the pipeline is designed to grant, by design, once
  approval passes — no host-level restriction is
  meant to contain that actor. Revisit only if the threat model changes
  (e.g. the production approval gate is weakened or removed).

## Open Questions

None remaining for this change. The deploy account's restriction mechanism
is settled above: a plain restricted user (ordinary `scp`/`ssh`, no forced
command at the SSH layer) whose *privilege* is scoped to a single fixed,
argument-free wrapper script via `sudoers` — not by `docker`-group
membership, and not by forwarding raw `docker compose` arguments through
`sudo` (both rejected; see Decisions). An `authorized_keys` `command=`
forced command (where the key can only ever trigger one fixed script at
the SSH layer itself, and the deploy workflow would need to pipe a tarball
over stdin instead of using `scp`) remains a future option if this shape
ever proves insufficient, but nothing in this change or its known
follow-up depends on revisiting it.
