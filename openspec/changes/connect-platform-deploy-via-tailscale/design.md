## Context

See proposal.md for why. `bootstrap-ansible-host-baseline`'s `deploy_user`
role is the pattern to mirror for a secret Ansible installs but doesn't
generate: the account's public key has no default and must be supplied
via Vault or a run-time variable (see that role's tasks/main.yml and
README.md). A Tailscale auth key is more sensitive than a public SSH
key — it grants tailnet-join capability — so it follows the same
out-of-band-generation pattern as the deploy account's *private* key, not
its public one.

Confirmed directly, not assumed: both the Hetzner cloud firewall (`hcloud_firewall`
rules in `terraform/modules/server/main.tf` are all `direction = "in"`,
nothing restricts outbound) and the host's UFW (the `hardening` role sets
`policy: allow` for `direction: outgoing`) already permit outbound
connections. Tailscale's client-to-coordination-server and
peer-to-peer/DERP-relay traffic is outbound-initiated on both the host and
the CI runner, so neither firewall layer needs a new *outbound* rule.

## Goals / Non-Goals

**Goals:**
- The deploy job can reach the host over SSH without widening
  `ssh_allowed_cidrs`/`hardening_ssh_allowed_cidrs` beyond the operator's
  own CIDR.
- The operator's own existing SSH access is unaffected.

**Non-Goals:**
- Configuring Tailscale ACLs (which nodes/tags can reach which other
  nodes/ports within the tailnet) — configured in Tailscale's own admin
  console/API, outside this repo's IaC. Noted as a real gap: without an
  ACL restricting it, any node on the tailnet can reach the host's
  tailnet-exposed SSH port, not just the CI-tagged ephemeral node. Left as
  follow-up since this tailnet has, at implementation time, only two
  members (the host and short-lived CI runners) — revisit if that changes.
- Migrating the operator's own SSH access to the tailnet — they keep their
  existing public-CIDR path; this change adds a second path for CI only.
- Removing or loosening `terraform/modules/server/variables.tf`'s
  `ssh_allowed_cidrs` validation — explicitly not touched, per proposal.md.

## Decisions

**One correction to the original dispatch's framing**: it assumed no UFW
change would be needed for SSH itself, reasoning that Tailscale traffic
"doesn't route through the public interface." That's true for the cloud
firewall (which only governs the public interface), but the host's own
UFW default-deny-incoming policy applies to *all* interfaces, including
the `tailscale0` one Tailscale creates — so without an explicit rule, UFW
would still block SSH arriving over the tailnet. A narrow UFW rule is
therefore required: allow SSH (22) via `src: 100.64.0.0/10` (the tailnet's
CGNAT range), matching this role's existing rules, which are all
`src:`-scoped rather than interface-scoped — not a fresh mechanism
introduced just for this rule. This is not a widening of the public-facing
rule the `0.0.0.0/0` validation guards — `100.64.0.0/10` isn't publicly
routable; only authenticated tailnet peers can present it as a source.

**Auth: Tailscale OAuth client for CI, a long-lived auth key for the
host.** The GitHub Actions side uses Tailscale's OAuth client mechanism
(Tailscale's documented, recommended approach for CI — `tailscale/
github-action`), which mints short-lived, auto-expiring node
registrations per run rather than reusing one long-lived key. The host
itself uses a conventional auth key (reusable, since Ansible re-applies
this role on every run and re-registering the same persistent node each
time is the expected behavior, not a security smell the way a long-lived
CI key would be).

**`PLATFORM_DEPLOY_HOST` is repointed, not duplicated.** The existing
secret already parameterizes every SSH/scp command in `platform-deploy.yml`
(`deploy-platform-compose-stack`'s design.md's Decisions). Updating its
value to the host's Tailscale address (a MagicDNS name or its `100.x.y.z`
tailnet IP) requires zero workflow code changes. Considered adding a
second secret (`PLATFORM_DEPLOY_HOST_TAILSCALE`) to keep the public IP
value around for reference — rejected: nothing in the workflow needs the
public IP anymore once this change lands, and an unused secret is a
liability (looks load-bearing, isn't), not a convenience.

**Tailscale role structure**: mirrors `deploy_user`'s shape — one role,
`tailscale_auth_key` variable with no default (required, out-of-band
generated), installed via Tailscale's official apt repository pinned to
an exact package version, consistent with this project's external-
dependency pinning convention.

## Risks / Trade-offs

- [Tailscale's apt repository may not yet publish packages for this
  host's Ubuntu codename (`resolute`) — the same class of problem
  `bootstrap-ansible-host-baseline` hit with Docker's repo, which turned
  out fine in practice but wasn't knowable in advance] → Not resolved
  here; flagged for whoever implements this to verify against the real
  host, same as the Docker case. If it doesn't have a `resolute` line,
  the fallback used for Docker (there wasn't one needed in the end, but
  the precedent is: check first, don't assume) applies here too.
- [No Tailscale ACL configured — any tailnet member can reach the host's
  tailnet-exposed SSH port] → Accepted for now (see Non-Goals); the
  tailnet is small and CI-only today. Revisit if more nodes join.
- [A second, independent connectivity path (the tailnet) now exists
  alongside the public SSH path — two things to keep secure instead of
  one] → Mitigated by scoping the tailnet rule as narrowly as the public
  one (SSH only, not a blanket "trust everything on tailscale0"), and by
  Tailscale's own device approval/key-expiry mechanisms in the admin
  console (operator-side, outside this repo).
