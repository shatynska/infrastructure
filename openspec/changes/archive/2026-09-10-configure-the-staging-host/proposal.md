## Why

Staging is provisioned and configured by nothing. `add-a-staging-environment`
gave it a Hetzner project, a server, an attached volume, an HCP workspace and an
ungated apply; `bootstrap-two-environments` then had to tell a company reader,
in `docs/bootstrap-a-new-host.md`'s "From here on, one host" section, that
everything from stage 5 onward configures the production host and that the
second server is a bare host with an unmounted volume.

Three mechanisms are named there as single-environment by construction. Two of
them are this change's: the host-baseline play targets `hosts: prod`, a literal
rather than a parameter, and the dynamic inventory authenticates with one
`HCLOUD_TOKEN`, which reaches one Hetzner project. The third — the platform
deploy workflow — is `docs/change-queue.md` entry 52 and stays there.

The second of the two fails quietly, which is why it is work rather than a
warning: a play whose `hosts:` matches nothing prints `skipping: no hosts
matched` and **exits 0**, so a converge that reached no host is indistinguishable
from one that had nothing to do — including in CI. Nothing in this repository
turns that into a failure today.

Two further entries are blocked behind this one. Entry 23 wants to move the host
converge into a gated workflow and needs a non-prod host to develop against —
that work wedges UFW or `tailscaled` if it is wrong, and doing it against prod
first is the thing staging exists to prevent. Entry 52 needs a converged host to
deploy a Compose stack to at all.

## What Changes

- **The host-baseline play takes the environment it configures as a parameter.**
  `hosts: "{{ target_environment }}"`, supplied per run. There is no default:
  a default would silently converge production on a run that forgot the flag.
- **The inventory grows one source per environment, each pinned to its own
  Hetzner token.** `ansible/inventory/hcloud.yml` becomes
  `ansible/inventory/prod.hcloud.yml` and `ansible/inventory/staging.hcloud.yml`,
  differing in the environment variable each takes its `api_token` from
  (`HCLOUD_TOKEN_PROD`, `HCLOUD_TOKEN_STAGING` — neither is the plugin's bare
  `HCLOUD_TOKEN` fallback, which stays Terraform's). A run names its inventory. Adding a
  third environment is adding one file and one variable, and no shell state can
  make a run reach the wrong project.
- **A play whose target group resolved to no host refuses.** A first play,
  against `localhost`, fails by name when the group named by
  `target_environment` is empty — turning the silent exit 0 into a refusal that
  says which environment resolved to nothing and under which token.
- **`ansible/inventory/group_vars/staging.yml`, written from scratch.** Its own
  CIDR mirrors (`hardening_web_allowed_cidrs: []`, matching staging's
  `web_allowed_cidrs = []`), its own operator account, its own `deploy_apps`
  entry for `platform` with a **staging-only** deploy keypair, its own
  Vault-encrypted GHCR token and heartbeat ping key under a `staging` vault id.
- **Staging converges with the same role set as prod**, `image_prune` included.
  Its weekly unit reports to its own heartbeat check, named from its own
  `inventory_hostname` (`staging-server-prune-host-images`).
- **Five refusal diagnostics stop naming production's own files.** Four name
  `ansible/inventory/group_vars/prod.yml` as where an input is set (`hardening`,
  `deploy_user`, and `image_prune`'s two); `platform_data_volume`'s names
  `terraform/environments/prod/terraform.tfvars` as where to check that the
  volume is attached. Telling an operator converging staging to look in
  production's files does not say where the input is expected to be set, which
  is what *A Role's Absent Required Input Is Reported by Name* already requires.
  This is a defect a second environment makes reachable, not a new rule.
- **The first converge of staging is run locally, by the operator**, exactly as
  `docs/bootstrap-a-new-host.md` §6.3 documents for prod. It is genesis rather
  than an exception to the never-apply-locally rule: CI reaches a host over the
  tailnet, and tailnet membership is created *by* the converge.
- **`docs/bootstrap-a-new-host.md` stops saying the second host cannot be
  configured.** "From here on, one host" loses two of its three bullets, and
  stage 6 becomes a stage run once per environment.

### Not in scope, and where it went instead

Entry 50 as written also lists the platform stack, staging's own hostnames and
DNS records, opening 80/443, and each application's staging deploy path. Entry
52 — recorded later, on 2026-09-10 — re-reads entry 50 as "the *host* half" and
claims the deploy mechanism for itself, and that reading is taken here. This
change leaves `web_allowed_cidrs = []` standing, adds no DNS record, and adds no
`PLATFORM_*` secret. What it does leave entry 52 is a converged host with a
`deploy` account already authorised for `platform` under a staging keypair, so
entry 52 needs no second converge to begin.

**But entry 52 does not claim all of it, and archiving deletes entry 50.** Entry
52's own text scopes itself to `platform-deploy.yml`'s `environment: production`
literal and the eight `PLATFORM_*` secrets. It says nothing about staging's DNS
records or about opening 80/443 — which entry 50 records as work, and which
`terraform/environments/staging/terraform.tfvars` records as deliberately not
done pending "the change that deploys the platform stack". Deleting entry 50
with nowhere for those to go would lose the only record of them, and would leave
`docs/deferred-work.md`'s "Managing DNS in Terraform" and "Four requirements
still stated over prod alone" pointing at an entry that no longer exists. So
this change opens an entry for staging's web exposure — the firewall change, the
hostnames, the certificates — and re-points both revisit triggers, before entry
50 is deleted rather than as a consequence of deleting it.

## Capabilities

### New Capabilities

None. Every requirement below belongs to the capability that already governs how
this repository configures a Terraform-provisioned host.

### Modified Capabilities

- `iac-host-configuration`: *Dynamic Inventory via hcloud Plugin* is MODIFIED —
  it currently obliges the plugin to authenticate with "the existing read-only
  `HCLOUD_TOKEN`, not a separate token", and states its scenario over the `prod`
  group. At one Hetzner project per environment that obligation is unsatisfiable
  for any environment but the first. Two requirements are ADDED to the same
  capability: one obliging the host-baseline play to name the environment it
  targets rather than carrying a literal, and one obliging a run whose target
  group resolves to no host to fail rather than exit 0.

## Impact

**Ansible.** `ansible/inventory/hcloud.yml` (renamed and split in two),
`ansible/inventory/group_vars/staging.yml` (new), `ansible/.envrc.example` (new),
`ansible/playbooks/host-baseline.yml` (parameterised `hosts:`, new guard play),
`ansible/ansible.cfg` (its `inventory =` default removed so no run silently
targets production, and `any_unparsed_is_failed` set so a source that cannot
authenticate fails the run instead of yielding an empty environment), and the
`fail_msg` of five assertions — in
`hardening`, `deploy_user`, `image_prune` (two) and `platform_data_volume`.
`ops_user`'s assertion names no environment-specific file and is untouched.

**Tests.** Two Molecule scenarios assert the literal string `group_vars/prod.yml`
in a refusal message — `hardening/molecule/absent-ssh-cidrs/verify.yml` and
`image_prune/molecule/absent-heartbeat-key/verify.yml` — and become obsolete in
their current form. New static assertions in `.github/tests/` cover the
inventory-per-environment layout, the play's parameterised target and the
presence of the guard play.

**Documentation.** `docs/bootstrap-a-new-host.md` (stages 1, 4.1, 4.3, 6, 9,
Appendix A, and the "From here on, one host" section), `.envrc.example`,
`README.md`'s local setup, `AGENTS.md`'s Inventory convention — which names
`ansible/inventory/hcloud.yml`, a path this change deletes — and the role
READMEs and `defaults/main.yml` comments that name prod's inventory file as the
place an input is set.

**Records.** `docs/change-queue.md` entry 50 is deleted on archive; entries 23
and 52 lose their block on it, and a new entry takes the web-exposure and DNS
work entry 50 was the only record of. `docs/deferred-work.md` is touched four
times: "Two gaps in required-input validation that only the play could close"
names this moment as its revisit trigger and is revisited here, "Managing DNS in Terraform" and "Four requirements still
stated over prod alone" both name entry 50 as their trigger and are re-pointed —
at the new web-exposure entry and at entry 52 respectively, since the second is
triggered by staging acquiring a persistent store rather than by its ports
opening; and "Four requirements still stated over prod alone" additionally gains
the two requirements that acquire a second subject the moment staging converges.

**External state the operator supplies, none of which exists today.** Staging's
Vault password, a staging Tailscale auth key, a staging `platform` deploy
keypair, staging's SSH host key recorded in the operator's `known_hosts`, and
staging's own heartbeat check with its period set. Listed in `tasks.md` as
prerequisites of the converge, not as discoveries during one — the host key
especially, since `ansible/ansible.cfg` sets `host_key_checking = True` and its
absence stops the first converge at connection time.

**Not touched.** `terraform/`, `platform/`, `.github/workflows/`. No credential
in this change reaches production, and nothing here applies anything from CI.
