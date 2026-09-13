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

## 1.6 — The Tailscale pair is recoverable after all, which removed a whole mechanism

**The operator holds both halves of the existing OAuth client**, confirmed 2026-09-13. So the pair is carried over like the other twenty values and **nothing in this change is reissued, replaced or invalidated**.

That is the third time this change priced work against a document saying a value was gone and found it was not. §0.3 says to delete each SSH private half once stored — they were not deleted. An earlier draft of `design.md` said `TF_API_TOKEN` could not be read back — it is in `~/.terraform.d/credentials.tfrc.json`. An earlier draft said an OAuth client secret, shown once at creation, could not be recovered — the operator has it.

**What it removed from the plan**: the task that created a replacement client, the task that revoked the old one, the rule deciding when revocation was permissible, and the design reasoning that held all three together. That reasoning had already been rewritten twice across review rounds 2 and 3 — first because reissuing late would have left `main-staging` holding a dead credential, then because revoking would have reached repositories outside this change's scope. None of it was needed.

### The finding that made revocation dangerous, kept because it stays true

`commerce-ops` holds `TAILSCALE_OAUTH_CLIENT_ID` and `TAILSCALE_OAUTH_SECRET` on its own `production` Environment — `gh api repos/shatynska/commerce-ops/environments/production/secrets` lists 20 secrets including both. That repository is live: `commerce-ops-app-1`, `commerce-ops-worker-1` and `commerce-ops-postgres-1` are running on the production host alongside the platform stack.

This is no longer this change's problem, because this change no longer revokes anything. It is recorded here rather than discarded because it remains true and it is the kind of fact that is expensive to rediscover: **whoever eventually rotates that OAuth client must treat `commerce-ops` as a holder**, and a secret's value cannot be read back, so no API call can establish whether it is the same client or a second one with the same tag. Only the Tailscale console can.

## Section 3, partial — two of six written 2026-09-13, during a GitHub incident

`main-staging` was created by the operator at 08:49:39Z and carries **no protection rules**, which is correct: staging is ungated by design.

Two of its six secrets are written and verified, both from sources this session holds:

| Secret | Source | `updated_at` |
|---|---|---|
| `ANSIBLE_SSH_PRIVATE_KEY` | `~/.ssh/shatynska-ansible-ci-main-staging` | 2026-09-13T08:56:03Z |
| `TF_API_TOKEN` | `~/.terraform.d/credentials.tfrc.json` | 2026-09-13T08:56:16Z |

Four remain and are the operator's: `ANSIBLE_VAULT_PASSWORD`, `HCLOUD_TOKEN` (staging's **Read & Write** token, not the read-only repository secret of a similar name), `TAILSCALE_OAUTH_CLIENT_ID` and `TAILSCALE_OAUTH_SECRET`.

### `gh secret set` reported failure on writes that succeeded

Measured rather than inferred, and worth keeping because it inverts the obvious reading of an error.

GitHub's secrets service was degraded throughout: the web UI answered *"Failed to load secrets"*, and the REST list endpoint returned `500`/`502` for every Environment holding secrets while answering instantly for an empty one. The repository-level list took 8.4s against a normal 0.4s. GitHub's status page reported all systems operational the whole time.

**Both writes to `ANSIBLE_SSH_PRIVATE_KEY` returned `HTTP 502`, and the secret exists.** A read taken immediately after the first attempt reported the Environment still empty, which read as confirmation that the write had failed; it had not. The `updated_at` of `08:56:03Z` belongs to the **second** attempt, which also reported `502`. The list endpoint then failed for several minutes before returning `2`.

So, for the four writes still to come and for section 6's fifteen:

- **A `5xx` is not evidence the write failed.** Verify by `updated_at`, never by exit status.
- **A read immediately after a write is not evidence either.** The list endpoint lagged the write by minutes.
- **Re-running a write was safe here only because the value was identical.** Two attempts with different values would have left the later one winning silently, with the error suggesting neither had.

This is why task 6.3 reads `updated_at` rather than the name list — an addition the fifth review round made for a different reason (a name list cannot distinguish a write from a name already present) which turns out to be the only reliable signal here too.

## Incidental observations, recorded rather than acted on

- The tailnet machine names are `main-production` and `main-staging` — the stack names, per `docs/naming-conventions.md`'s rule that a server's name reaches the tailnet and therefore carries its stack. The hosts' own hostnames are `shatynska-main-production` and `shatynska-main-staging`, templated by the converge from the `company` group variable. Both are correct under the scheme and the divergence is deliberate; noted because reading the two side by side invites the conclusion that one of them is wrong.
- `main-staging`'s host is up and reachable, so staging is a live stack rather than a disabled one. Task 4.7's dispatched staging converge therefore has a host to converge.
