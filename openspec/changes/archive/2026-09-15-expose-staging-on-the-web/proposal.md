## Why

Staging runs the platform stack and has no way in from the public internet: `web_allowed_cidrs = []` in `terraform/stacks/main-staging/terraform.tfvars`, so its Hetzner cloud firewall carries no rule for 80 or 443. `docs/backlog.md`'s `expose-staging-on-the-web` records that as deliberate until something is there to reach.

The operator has decided to open them now, ahead of the first application deploy, and the reason is that the application is waiting on this rather than the reverse. `commerce-ops`'s own change `deploy-commerce-ops-to-staging` (in the `commerce-ops` repository, opened 2026-09-14) names this entry as what stands between its staging hostname and the application: both of its Slack apps take HTTP request URLs and its ClickUp webhook registers against its public base URL, so a staging deploy is not usable without inbound web traffic, and `register_clickup_webhook` runs at container start, so the deploy that follows this change is the one that registers it.

The DNS half of the entry already exists, made by the operator outside any repository. Read over public DNS on 2026-09-14: `*.main-staging.fincci.bike` A `62.238.17.177` — staging's public address, which is also what Hetzner's metadata service on the host reports — and `staging.shatynska.com` A `62.238.17.177`. `commerce-ops.main-staging.fincci.bike`, the name that change will route, resolves through the wildcard.

## What Changes

- **Open 80 and 443 on staging's cloud firewall to `0.0.0.0/0`**, production's value: `web_allowed_cidrs = ["0.0.0.0/0"]` in the staging stack's `terraform.tfvars`. The module adds the two rules in place; no resource is replaced.
- **Mirror it at the host layer**: `hardening_web_allowed_cidrs: ["0.0.0.0/0"]` in `ansible/inventory/group_vars/staging.yml`. UFW is not in the path for Traefik's container-published ports (`docs/backlog.md`'s `say-what-the-host-firewall-actually-gates`), but the mirror obligation between the two files stands, as that entry itself says.
- **Correct every statement the opening falsifies**: the `web_allowed_cidrs` description in `terraform/stacks/main-staging/variables.tf`; `ansible/roles/hardening/README.md`'s per-environment sentence; `docs/backlog.md`'s `say-what-the-host-firewall-actually-gates`, which quotes the bootstrap sentences being rewritten and says staging reaches no public web port; in `docs/bootstrap-a-new-host.md`, the end-state bullet, the *Time* paragraph, the prerequisites table's DNS row, §1.3's decision table, §4.4's instruction not to point a hostname at staging, the "What still differs" bullet after §4.4, stage 6's `group_vars` row and UFW check, Appendix B's claim that a staging rebuild owes no DNS edit, and Appendix C's; `README.md`'s pointer to what staging still needs; and `docs/backlog.md`'s `refresh-staging-group-vars-banner`, which owns `README.md`'s staging-status paragraph and gains that its "no DNS records" is now false too.
- **Record the DNS that exists**: §4.4 is "where the zone is written down" and describes only `shatynska.com`. Add the `fincci.bike` zone's server wildcards and `staging.shatynska.com`, and resolve §4.4's revisit trigger, which names this entry.
- **Record in `docs/backlog.md` the one thing this change finds and does not take**: the `<service>.<server>.<base domain>` hostname rule the `commerce-ops` handoff says belongs in `docs/naming-conventions.md`.
- On archiving, delete backlog entry `expose-staging-on-the-web` and correct `say-what-the-host-firewall-actually-gates`'s sentence that cites it.

### Not in scope

- **No router, dummy or otherwise.** Staging has no application, so Traefik declares no router and requests no certificate; this change does not add one to make an issuance observable. The first certificate issues when `commerce-ops`'s staging deploy lands, with no further change here.
- **Closing container-published ports at the host layer** (`DOCKER-USER`, loopback publishing) — that is `say-what-the-host-firewall-actually-gates`'s question and is not prejudged.
- **Managing DNS in Terraform.** The migration stays declined; see design.md.
- **Production**, whose values are unchanged.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None, so `.openspec.yaml` carries `skip_specs: true`. No requirement in `openspec/specs/` states staging's web ports or its DNS: the firewall's web rule is a module behaviour driven by a variable (`terraform/modules/server/tests/firewall.tftest.hcl` already covers both the empty and the open case), and which value a stack gives it is configuration. No derived tests are owed; the suites stay green.

## Impact

- `terraform/stacks/main-staging/terraform.tfvars` — on merge, `apply.yml` applies staging's saved plan with no reviewer, since `main-staging` requires none.
- `ansible/inventory/group_vars/staging.yml` — on merge, `host-converge.yml` converges staging unattended and adds two UFW rules; production's converge is unaffected in effect.
- `terraform/stacks/main-staging/variables.tf` (a description only), `ansible/roles/hardening/README.md`, `docs/bootstrap-a-new-host.md`, `docs/backlog.md`, `README.md`.
- **Exposure**: the only listener on staging's public interface is `platform-traefik-1` on `0.0.0.0:80` and `0.0.0.0:443` (probed 2026-09-14 with `docker ps`); Grafana publishes on the tailnet address only, and every other service publishes nothing. Traefik has no API or dashboard enabled and no router, so the public internet receives a `301` on 80 and a `404` behind Traefik's default certificate on 443 — what the tailnet already receives today.
