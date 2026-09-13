# Credential audit — section 1, performed 2026-09-13

`tasks.md` 1.1 requires the live state recorded in this change rather than trusted from `handoff.md`. This is that record. Everything here is a read; nothing was written to any Environment, any host or any external service.

## 1.1 — The live Environment state

    gh api repos/shatynska/infrastructure/environments

| Environment | Created | Protection rules |
|---|---|---|
| `main-production` | 2026-09-12T06:11:52Z | `required_reviewers` |
| `production` | 2026-07-26T06:02:23Z | `required_reviewers` |
| `staging` | 2026-09-10T08:14:33Z | none |

`main-staging` does not exist. `main-production` carries its reviewer, which `tasks.md` 6.1 re-reads anyway because this is the claim that has already gone stale once.

## 1.2 — The secret names

**`production`, 15** — `ANSIBLE_SSH_PRIVATE_KEY`, `ANSIBLE_VAULT_PASSWORD`, `HCLOUD_TOKEN`, `PLATFORM_ACME_EMAIL`, `PLATFORM_DEADMANSWITCH_URL`, `PLATFORM_DEPLOY_HOST`, `PLATFORM_DEPLOY_SSH_KEY`, `PLATFORM_GRAFANA_ADMIN_PASSWORD`, `PLATFORM_POSTGRES_EXPORTER_PASSWORD`, `PLATFORM_POSTGRES_PASSWORD`, `PLATFORM_POSTGRES_USER`, `PLATFORM_SLACK_WEBHOOK_URL`, `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_SECRET`, `TF_API_TOKEN`.

**`staging`, 6** — `ANSIBLE_SSH_PRIVATE_KEY`, `ANSIBLE_VAULT_PASSWORD`, `HCLOUD_TOKEN`, `TAILSCALE_OAUTH_CLIENT_ID`, `TAILSCALE_OAUTH_SECRET`, `TF_API_TOKEN`.

Both lists match `handoff.md` exactly. Nothing was added between the handoff being written and this audit, so the carry-over set is the set the plan was built on.

## 1.3 — The three SSH private halves are working keys

All three verified, and the two that could not be proven from the repository are now proven by login **over the tailnet**, which is the path the converge actually takes rather than a public address:

| Key | Check | Result |
|---|---|---|
| `~/.ssh/shatynska-platform` | derived public half vs. `deploy_apps[platform].public_key` in `ansible/inventory/group_vars/production.yml` | byte-identical |
| `~/.ssh/shatynska-ansible-ci-main-production` | `ssh -i … root@100.88.198.111` | authenticated; host answered `shatynska-main-production` |
| `~/.ssh/shatynska-ansible-ci-main-staging` | `ssh -i … root@100.85.219.36` | authenticated; host answered `shatynska-main-staging` |

**What this establishes and what it does not.** Each key is accepted by the host it is for, and the platform key matches the public half this repository commits. None of it establishes that a file equals the value GitHub stores — nothing outside GitHub can. That remains the inference `design.md`'s Risks section names, and the ordering is still what covers it: the new Environment is populated from these files and a converge is observed under it before anything old is deleted.

The keys were renamed onto `docs/naming-conventions.md`'s workstation scheme on the same day (`docs/change-queue.md` entry 84); the paths above are the current ones.

## 1.4 — The two values recovered off the running deployment

Both read back exactly rather than reconstructed, from the deployment that is using them:

- **`PLATFORM_ACME_EMAIL` = `helenshatynska@gmail.com`**, from `platform-traefik-1`'s command line: `--certificatesresolvers.letsencrypt.acme.email=…`.
- **`PLATFORM_DEPLOY_HOST` = `100.88.198.111`**, from `platform-grafana-1`'s `GF_SERVER_ROOT_URL=http://100.88.198.111:3000`, which the deploy renders from that secret. It is the tailnet IPv4 form rather than the machine name — `docs/bootstrap-a-new-host.md` permits either and says they fail differently, so the form matters and is recorded here.

## 1.5 — `TF_API_TOKEN` is on the workstation

`~/.terraform.d/credentials.tfrc.json` holds a token for `app.terraform.io`, where `terraform login` put it. It is **recovered, not reissued**. `docs/change-queue.md` entry 75 recorded this and an earlier draft of `design.md` denied it; entry 75 was right.

## 1.6 — The Tailscale client is held outside this repository, and that decides task 9.4

**`commerce-ops` holds it.** `gh api repos/shatynska/commerce-ops/environments/production/secrets` lists 20 secrets including `TAILSCALE_OAUTH_CLIENT_ID` and `TAILSCALE_OAUTH_SECRET`. That repository is real and running: `commerce-ops-app-1`, `commerce-ops-worker-1` and `commerce-ops-postgres-1` are up on the production host alongside the platform stack.

Task 9.4's rule applies directly: an Environment defining `TAILSCALE_OAUTH_CLIENT_ID` counts as a holder **unless that repository's own client ID is confirmed distinct from the Tailscale console**. A secret's value cannot be read back, so `gh` cannot settle which client it is. So unless the operator confirms from the console that `commerce-ops` uses a different client, **the old client is not revoked**, and task 9.4's default branch — leave it live, record the decision, open a queue entry for the wider rotation, and correct the runbook's Appendix A row — is the one that applies.

This was found in section 1 rather than at section 9, which is where it would have been expensive. It is the concrete instance of the hazard the third review round raised as a possibility.

**Still outstanding in 1.6**, and an operator action: confirming the *scope and tag* of the client to be created at 3.2 against the old one — Auth Keys: Write, `tag:ci` per the runbook's stage 5.

## Incidental observations, recorded rather than acted on

- The tailnet machine names are `main-production` and `main-staging` — the stack names, per `docs/naming-conventions.md`'s rule that a server's name reaches the tailnet and therefore carries its stack. The hosts' own hostnames are `shatynska-main-production` and `shatynska-main-staging`, templated by the converge from the `company` group variable. Both are correct under the scheme and the divergence is deliberate; noted because reading the two side by side invites the conclusion that one of them is wrong.
- `main-staging`'s host is up and reachable, so staging is a live stack rather than a disabled one. Task 4.7's dispatched staging converge therefore has a host to converge.
