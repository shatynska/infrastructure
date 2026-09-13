# Naming conventions

How everything this repository creates is named, and the one rule the scheme follows.

> **IN EFFECT, WITH ONE EXCEPTION.** This document records a decision taken on 2026-09-11. It arrived through `docs/change-queue.md` entries 61, 62, 63 and 64, all four archived, and the tree matches it everywhere the scheme reaches — except the two **GitHub Environments**, which are `production` and `staging` where the scheme calls for `main-production` and `main-staging`. Entry 75 is what would move them, and the paragraph below is why it has not. Read every other name here as describing the tree; read the GitHub Environment row as describing the target. Whoever archives 75 deletes this banner.
>
> **Entry 75 was not in the original four and is the one name this scheme cannot buy cheaply.** Entry 63 was scoped to rename the two GitHub Environments along with the workspaces, the repository secrets and the Hetzner projects, and found that GitHub offers no way to rename a deployment Environment at all — so moving one means re-creating it and re-entering every secret it holds, three of which are SSH private halves this repository's own bootstrap has the operator delete once stored. That was deferred rather than paid. **A new deployment pays nothing**, because it names its Environments correctly when it creates them; `docs/bootstrap-a-new-host.md` §3.2 says so at the moment of choosing.

## The rule

**Qualify a name where its namespace is shared; leave it short where the namespace already belongs to one thing.**

Every decision below falls out of that. A Hetzner firewall never leaves its project, so it is called `main`. A server's name reaches the tailnet and the heartbeat service, both of which hold every stack a company owns, so it carries the stack it belongs to.

## What each namespace is scoped to

This table is the reason the scheme looks uneven, and it is worth reading before disagreeing with any particular name.

| Namespace | Scoped to | Consequence |
|---|---|---|
| Hetzner server, firewall, volume, SSH key names | one **project** | a name is free in every other project |
| Hetzner volume device path (`scsi-0HC_Volume_<id>`) | the volume's **id** | the on-host mount path is independent of the volume's name |
| GitHub Environment, repository secret | one **repository** | free in the company's clone |
| HCP workspace | one **organisation** | one organisation per company |
| Terraform state | one **workspace** | two stacks may never share one |
| Ansible `inventory_hostname` | the Hetzner **server name** | renaming a server renames its Ansible identity |
| Heartbeat check slug | one **account** | one account per company, holding every stack |
| Tailnet machine name | one **tailnet** | one tailnet per company, holding every stack |
| `~/.ssh/`, SSH aliases, checkouts | one **workstation** | shared between every company you operate |

Two of those are shared **per company rather than per project** — the tailnet and the heartbeat account — and that is the single fact the server's name exists to respect. Two hosts sharing a heartbeat slug do not fail loudly: the live one's weekly success keeps the check green while the other's timer is dead, which is the masking failure `docs/bootstrap-a-new-host.md` Appendix C names.

## The axes

| Axis | Values | Where it appears |
|---|---|---|
| **company** | `shatynska`, `fuperia` | the workstation, and the host's own hostname. Nowhere in Hetzner, HCP or GitHub — each of those boundaries already belongs to one company |
| **tenant** | `main`, and later a named system | the stack name |
| **environment** | `production`, `staging` | the stack name. Spelled in full, always — `prod` and `preprod` prefix-collide, and one spelling is worth more than four characters |
| **rank** | `main` | project-local resources distinguished by rank rather than by identity |
| **identity** | `operator`, and later `deploy`, `ci` | resources distinguished by *what they authenticate* rather than by rank |

There is deliberately **no role axis** (`web`, `db`, `edge`). Every role field appears when a tenant is split across several hosts, and this project's answer to that is a managed service rather than a second host. If one is ever needed it appends without disturbing anything above it.

## The stack is the only identifier

A **stack** is one Terraform root module: one state, one Hetzner project, one blast radius. Its name is `<tenant>-<environment>`, and everything else is derived from it rather than chosen separately.

    stack name                 main-production
      ├── directory            terraform/stacks/main-production/
      ├── GitHub Environment   main-production     (entry 75; see the banner)
      ├── HCP workspace        main-production
      ├── Hetzner project      main-production
      ├── read-only secret     HCLOUD_TOKEN_MAIN_PRODUCTION     (upper-cased, - → _)
      ├── inventory source     ansible/inventory/main-production.hcloud.yml
      └── server               main-production

Tenant before environment, because a tenant outlives the environments it has and some tenants will have only one. Adding a tenant is adding a directory; a tenant with no staging is simply a tenant with one stack, and nothing notices the absence.

**The write secret is the exception that needs no suffix.** `HCLOUD_TOKEN` inside each GitHub Environment is correct as it stands: Environments namespace their own secrets. The read-only token needs the stack in its name only because *repository* secrets are one flat namespace, and the plan and drift jobs deliberately declare no `environment:` — which is what keeps the write token out of their reach.

## Every name

| What | Name | Why this and not something shorter or longer |
|---|---|---|
| stack directory | `terraform/stacks/main-production/` | `stacks/` names the invariant — one state, one plan — rather than the contents |
| labels | `tenant=main`, `environment=production`, `managed_by=terraform` | orthogonal axes belong in labels, which are queryable; a name can only carry one ordering |
| Ansible groups | `main` and `production`, one per label | a tenant-wide baseline and an environment-wide baseline, without special-casing a tenant that has no staging |
| **server** | `main-production` | the one name that leaves its project. Unique per **company**, not per project |
| firewall | `main` | project-local, and distinguished by rank |
| volume | `main` | project-local. `-data` was the server's role leaking into the volume's name |
| mount path | `/mnt/main` | identical in every stack, which is what lets `platform/docker-compose.yml` stay unparameterised |
| SSH key | `operator` | keys are distinguished by what they authenticate, never by rank. See below |
| heartbeat slug | `main-production-prune-host-images` | derived from `inventory_hostname`; carries no company because the account holds one |
| OS hostname | `shatynska-main-production` | the only repository-side value that reaches a workstation serving two companies |

## Rank words and identity words

`main` answers *which of several?* — it is the right word for a volume or a firewall, where a second one would be the extra one. It is deliberately not `default`, which reads as though nobody chose, and not `primary`, which drags in replication vocabulary.

An SSH key is not distinguished by rank. A second key here would be a deploy key, a CI key, or another person's — so keys take the identity axis, and this one is `operator` because that is what it is: the operator's root credential, whose workstation half is `~/.ssh/<company>-root`.

## The hostname, and the two names a host has

`inventory_hostname` is `main-production` and the host's own hostname is `shatynska-main-production`. That divergence is the rule doing its job rather than an oversight: `inventory_hostname` lives inside a repository that belongs to one company, and the hostname is read on a laptop that serves two.

**Nothing sets the hostname today.** Cloud-init sets it once, at creation, from the Hetzner server name — so renaming a server in Terraform does not rename the running host, and a stack renamed without an Ansible hostname task leaves the host answering to its old name forever. The task is part of entry 62 for that reason, and the hostname it templates is `{{ company }}-{{ inventory_hostname }}`, with `company` a single group variable that the company's clone changes once.

## The workstation

The only namespace shared between companies, and the only place the company appears as a literal.

| | `shatynska` | `fuperia` |
|---|---|---|
| checkout | `~/projects/shatynska-infrastructure` | `~/projects/fuperia-infrastructure` |
| root key | `~/.ssh/shatynska-root` | `~/.ssh/fuperia-root` |
| operator key | `~/.ssh/shatynska-ops` | `~/.ssh/fuperia-ops` |
| SSH alias | `ssh shatynska-main-production` | `ssh fuperia-main-production` |
| converge key, **one per stack** | `~/.ssh/shatynska-ansible-ci-main-production` | `~/.ssh/fuperia-ansible-ci-main-production` |

**The converge key carries the stack, not the environment**, and it is the only per-stack artefact whose name lives on a workstation rather than in a namespace some service owns. That is what made it the last one to move: nothing reads the filename — the private half goes into a GitHub Environment secret and the public half into a host's `authorized_keys`, and neither carries it — so no check can hold this name and only the runbook states it. Two stacks made `-production` and `-staging` distinct by luck; a second tenant would have collided, which is the collision `HCLOUD_TOKEN_MAIN_PRODUCTION` carries four extra characters to avoid one namespace over.

**Pin every alias to an explicit `HostName`.** A bare alias resolved by MagicDNS follows whichever tailnet profile is active, so `ssh main-production` with two tailnets is a command whose destination depends on a setting you cannot see in it.

## Growth

| What arrives | What it costs |
|---|---|
| a second environment for a tenant | a directory. `main-staging`, and every derived name follows |
| a tenant with no staging | nothing. One stack instead of two |
| a third tenant | a directory. `analytics-production` |
| a second company | a clone of this repository, a Hetzner account, an HCP organisation, a tailnet and a heartbeat account of its own — and one group variable changed |
| a second volume in one stack | a name on the rank axis beside `main`: `backups`, `media` |
| a second server in one stack | the only shape that costs a rename. The role axis appends — `main-production-main` beside `main-production-db` — and the existing server is renamed once rather than left as the unmarked default |

## What a name must never carry

Region, size, image, IP address, owner, or anything else that can change without the thing itself changing. Those go in labels, which are queryable and which nothing else is derived from.

**One company per Hetzner account, HCP organisation, tailnet and heartbeat account.** Sharing any of the four puts two companies in one namespace, and the name that namespace holds would then need the company in it. The heartbeat account is the one to watch: sharing it fails silently, and it fails in the direction of a green check.
