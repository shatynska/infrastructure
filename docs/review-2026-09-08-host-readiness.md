# Host readiness review, 2026-09-08

A map of this repository as it stood at trunk `74c7101`, read to answer one question: can its shape be reused, mostly unchanged, for a second Hetzner host owned by a company that will run several small services on it? The review read the tree, the live `main-server` host over SSH as `ops-claude`, the Hetzner API with the read-only token, the GitHub repository settings, and the one application currently deployed. Nothing was changed by it.

**Verdict.** The architecture fits and needs no restructuring. The gaps are operational: they concern the data on the host and the ability to recover it, not the ability to change it safely. Every gap that applies to this host too was recorded as an entry in `docs/change-queue.md`; this document is the map those entries hang off, and it does not repeat their detail.

**This is a dated record and is not maintained.** Everything below is what was read on 2026-09-08 and stays written as it was read, including the gaps since closed. Where a row names a queue entry that no longer exists, the note beside it says what became of it; the queue itself is the current list, and this document is not.

## How the system is built

Three layers, each with its own path to production and its own verification. The boundary between them is the design decision everything else rests on.

| Layer | Directory | What it owns | Reaches production by | Verified by |
|---|---|---|---|---|
| Provision | `terraform/` | Server, firewall, SSH key, data volume | `apply.yml`: saved plan, `production`-gated apply, destroy-policy gate | `terraform test`, fmt, validate, tflint, Trivy, PR plan comment, nightly drift |
| Configure | `ansible/` | Docker, UFW and fail2ban, tailnet, `deploy` and operator accounts, data-volume mount, image prune | A hand-run `ansible-playbook` from a workstation | Molecule per role (required check), ansible-lint, syntax check |
| Run | `platform/` and each application repository | Traefik, shared Postgres, monitoring; each app's own Compose stack | `platform-deploy.yml` and each app's `deploy.yml`: tar over forced-command SSH via the tailnet, `up -d --wait` | `docker compose config` on PRs, healthchecks at deploy |

Cross-cutting: `.github/tests` asserts the pipeline's own configuration and repository-wide conventions statically; `openspec/` records every requirement and every change; `docs/` holds what is queued and what is deferred.

The host as observed: `cx33` (4 vCPU, 8 GB, 80 GB root) in `hel1`, Ubuntu 26.04, one 10 GB volume at `/mnt/main-data` holding Prometheus and Grafana state, eleven containers, of which three belong to commerce-ops. Root disk 15% used. Daily Hetzner snapshots, seven retained.

## What to keep

These are the parts that make the shape worth copying. None of them needs changing for a second host.

- **The gated Terraform path.** The plan a reviewer approves is the plan that applies. The read-only token is the only one an automatic job ever holds. Deletes and replaces fail the run unless the merged PR was labelled for them. Drift is detected nightly and tracked as an issue. Delete and rebuild protection and backups are on.
- **The application deploy contract.** One `deploy` account; per application one key bound to one forced command, one sudoers line naming one fixed invocation, one `/opt/<name>` directory. The tar extracts exactly two named members. The host is reachable only over the tailnet. `up -d --wait` fails the job on an unhealthy service, and the previous deploy's images are reclaimed afterwards. Onboarding a service is a keypair, an inventory entry and a copied workflow. This is the part a company with many services benefits from most.
- **Roles tested for their failure paths.** Molecule scenarios cover a rejected registry credential, a missing volume, a revoked operator, a malformed application list. The suite gates merges.
- **A pipeline that checks itself.** The `.github/tests` suite catches the class of rot a reviewer cannot: a module added without Dependabot coverage, a citation that breaks on archive, a required check shaped so it never reports.
- **Monitoring proportionate to one host.** Host, container, Postgres and per-router HTTP metrics; alerts to Slack; an external dead-man's switch; real healthchecks on every platform service; bounded retention on dedicated storage; Grafana on the tailnet only.
- **Everything pinned, every decision written down.** Galaxy content, pip toolchain, Actions, providers, images, the Molecule base image by digest. The reasoning behind each non-obvious choice is in the file that makes it.

## Where it falls short

Ordered by consequence for a business host. The last column says whether the finding was recorded for this host, and where.

| # | Finding | Evidence | Applies to | Recorded |
|---|---|---|---|---|
| 1 | No logical database backup, no off-host copy, no recorded restore | Hetzner snapshots are root-disk only; volume excluded; Postgres data in a Docker volume, captured crash-consistently once a day | Both | **Resolved** by `scope-the-shared-database-to-non-durable-data`, which answered it as a classification rather than a backup: no *platform-stack* store holds data requiring one, and durable data is not to be kept on this host. The gap this row names survives in one place the requirement names as a divergence — `commerce-ops`'s own PostgreSQL — tracked as queue entry 33 |
| 2 | The shared-Postgres requirement is not what the host does | `commerce-ops-postgres-1` runs its own instance; the platform instance lists no application database; provisioning is "not yet defined" in `platform/README.md` | Both | **Resolved** by the same change, which narrowed the requirement to non-durable data and named the `commerce-ops` container as a divergence in the requirement itself |
| 3 | Container logs are unbounded | `json-file` driver, no `daemon.json`, empty `LogConfig` on every container | Both | Queue 21 |
| 4 | No swap, no container resource limits | `swapon --show` empty; no `deploy.resources` anywhere in `platform/docker-compose.yml` | Both | Queue 7 and 22 |
| 5 | Host configuration ships from a workstation | No workflow runs the playbook; Vault password and tailnet key are local | Both | Queue 23 |
| 6 | The pipeline is single-environment | `apply.yml`, `drift.yml`, `pr-validation.yml` and the playbook name `prod` literally | Both | Queue 24 |
| 7 | Public SSH open from one ISP range; sshd and unattended-upgrades run on image defaults | Cloud firewall and UFW allow 22 from `176.104.184.0/24`; tailnet rule already admits SSH; no sshd drop-in on the host | Both | Queue 25 |
| 8 | DNS lives outside every repository | Nothing in the tree names a DNS record | Both | Queue 26 |
| 9 | No check from outside the host that a public hostname answers | Watchdog proves Alertmanager is alive, not that customers reach a service; no TLS-expiry alert | Both | Queue 27 |
| 10 | Logs are per container, over SSH, lost on redeploy | No Loki or equivalent in the stack | Both, later | Queue 28 |
| 11 | Traefik has no global HTTPS redirect or default resolver | Each app must repeat two labels per router; a forgotten one serves plain HTTP silently | Both | Queue 29 |
| 12 | Rebuilding the host has never been done in sequence | Steps span four repositories and two READMEs, in no stated order | Both | Queue 30 |
| 13 | ~~Platform image pins are not watched by Dependabot~~ | ~~`dependabot.yml` covers `terraform` and `github-actions` only~~ | Both | **Closed** by `cover-platform-images-with-dependabot`: a third ecosystem, `docker-compose` over `/platform` |
| 14 | The repository is public and commits the operator's CIDR and tailnet hostnames | `gh api repos/.../infrastructure` reports `visibility: public` | Company host only | Not recorded; a choice for this host |
| 15 | One person authors, reviews and approves | Branch protection requires 0 reviews; the `production` Environment has one reviewer | Company host only | Not recorded; a team setting, not a repository one |
| 16 | The workflow ceremony assumes an agent operator and one approver | OpenSpec gates, six-round review loops, comment density | Company host, if human engineers join | Not recorded; a process decision |

## Reading the map for a second host

The order to work in, if the goal is a company host that can be trusted with commerce data:

1. ~~Entries 19 and 20 together: decide the database model, then back it up. Nothing else on this list protects data.~~ Done, and not the way this line assumed: reading the host showed the instance those entries argued over holds no application data, so the answer was a stated boundary — durable data lives in an external managed service, and no platform-stack store needs a backup — rather than a pipeline. One divergence outlives it, recorded as such in the requirement and tracked as queue entry 33: `commerce-ops`'s own database.
2. Entries 21 and 22: log rotation and swap. Cheap, and they turn two classes of outage into alerts.
3. Entry 24, then 23: make the pipeline environment-aware, then move the host converge into it. Staging is where the rest gets rehearsed.
4. Entries 25 and 29: hardening and Traefik defaults. Each is small on its own. Entry 26, DNS as code, is no longer on this list: reading the zone showed it is served by ukraine.com.ua and carries live MX and SPF, so managing it in Terraform means an NS migration that moves mail — declined for now and recorded in `docs/deferred-work.md`, where the records themselves are written down, which is most of what this line was protecting against. Entry 31, Dependabot for images, was the fourth and is done — and turned out not to be the one-stanza edit it was queued as: the requirement it lands in enumerates its ecosystems by name, and a test reads that enumeration back.
5. Entries 27 and 30: external checks and the rebuild runbook. These are what turn "the host can be rebuilt" into "we know it can, and how long it takes" — no backup is restored in that sequence, and entry 30 was rewritten to say so.
6. Entry 28 when the second or third service lands.

For a company-owned copy, additionally: a private repository in the company organisation, a `production` reviewer who is not the author, and a decision about how much of the OpenSpec workflow to carry across. Those are settings and policy, not code, which is why they have no queue entry here.
