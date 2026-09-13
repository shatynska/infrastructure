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

## Section 3, complete — `main-staging` built 2026-09-13, during a GitHub incident

`main-staging` was created by the operator at 08:49:39Z and carries **no protection rules**, which is correct: staging is ungated by design.

All six secrets are written and verified by `updated_at`, and the name list equals `staging`'s from 1.2 exactly:

| Secret | Written by | `updated_at` |
|---|---|---|
| `ANSIBLE_SSH_PRIVATE_KEY` | this session, from `~/.ssh/shatynska-ansible-ci-main-staging` | 08:56:03Z |
| `TF_API_TOKEN` | this session, from `~/.terraform.d/credentials.tfrc.json` | 08:56:16Z |
| `ANSIBLE_VAULT_PASSWORD` | operator | 09:34:05Z |
| `TAILSCALE_OAUTH_CLIENT_ID` | operator | 09:36:05Z |
| `TAILSCALE_OAUTH_SECRET` | operator | 09:36:29Z |
| `HCLOUD_TOKEN` | operator | 09:37:20Z |

`main-staging` carries **no protection rules**, matching `staging`'s deliberate ungated design, and was created at 08:49:39Z.

### The GitHub incident this section was performed during

GitHub posted **"Incident with several GitHub Services"** at 09:16:11Z, impact **critical**, affecting *API Requests, Issues, Pull Requests, Actions and Pages*. Its 09:36Z update named the cause: *"increased database replication delays on collab which is causing increased error rates in authorization endpoints and follow-on increased error rates across the system"*.

**The errors were visible from this session well before the incident was posted**, which is the normal lag rather than a contradiction — an earlier check of the status page during the same failures reported all systems operational. A status page saying nothing is wrong is not evidence that nothing is wrong.

It was established as GitHub's rather than this change's by four reads: `staging`'s secrets failed although neither the operator nor this session had touched that Environment all day; `commerce-ops`, a different repository entirely, failed the same way; non-Actions endpoints on this repository answered instantly; and repository-level secrets still answered. One component failing across several repositories is the opposite signature from a repository this change had damaged.

**Replication lag is why the reads disagreed with themselves**, and it bounds how far to trust them. A lagging replica can hide a write that happened; it cannot invent one that did not. So the six names reading back with today's timestamps is trustworthy in the direction that matters, while the earlier read showing an empty Environment after a successful write is exactly what a stale replica looks like.

### `gh secret set` reported failure on writes that succeeded

Measured rather than inferred, and worth keeping because it inverts the obvious reading of an error.

GitHub's secrets service was degraded throughout: the web UI answered *"Failed to load secrets"*, and the REST list endpoint returned `500`/`502` for every Environment holding secrets while answering instantly for an empty one. The repository-level list took 8.4s against a normal 0.4s. GitHub's status page reported all systems operational the whole time.

**Both writes to `ANSIBLE_SSH_PRIVATE_KEY` returned `HTTP 502`, and the secret exists.** A read taken immediately after the first attempt reported the Environment still empty, which read as confirmation that the write had failed; it had not. The `updated_at` of `08:56:03Z` belongs to the **second** attempt, which also reported `502`. The list endpoint then failed for several minutes before returning `2`.

So, for the four writes still to come and for section 6's fifteen:

- **A `5xx` is not evidence the write failed.** Verify by `updated_at`, never by exit status.
- **A read immediately after a write is not evidence either.** The list endpoint lagged the write by minutes.
- **Re-running a write was safe here only because the value was identical.** Two attempts with different values would have left the later one winning silently, with the error suggesting neither had.

This is why task 6.3 reads `updated_at` rather than the name list — an addition the fifth review round made for a different reason (a name list cannot distinguish a write from a name already present) which turns out to be the only reliable signal here too.

## Section 4 observed — staging's apply ran under `main-staging`, unattended

PR #167 merged at 2026-09-13T10:33:07Z as `5976efd`. The evidence for task 4.7, read from the run rather than inferred from a green check:

| Fact | Evidence |
|---|---|
| The apply attached to the **new** Environment | A deployment record for environment `main-staging` created at 10:33:44Z — the first ever under that name; every prior record reads `staging` |
| It did **not** wait for a reviewer | `plan (main-staging)` completed 10:33:36Z, `apply (main-staging)` started 10:33:47Z and completed 10:33:59Z — eleven seconds, no pause |
| Production was not touched | Only `main-staging` appears in the run's jobs, which is the affected-stack rule working: the merge changed `terraform/stacks/main-staging/` and no other stack directory |

**That staging applies unattended is the design, not a defect**, and it is what makes staging worth using as a canary: the whole create-populate-verify-flip-observe sequence has now been exercised where a mistake costs a re-run rather than a production approval.

It also exercised the re-entered `HCLOUD_TOKEN` and `TF_API_TOKEN` on `main-staging` — a successful `terraform apply` cannot be reached with either of those wrong. What it does **not** exercise is the converge key, the vault password or the Tailscale pair, which is why task 4.8 dispatches a staging converge before production's half begins.

**Performed during the GitHub incident** and succeeded anyway: Actions was `degraded_performance` and Pull Requests `major_outage` when the pull request was opened, yet every check and both jobs completed. The pull request body records that window so a later reader does not mistake the timing for a cause.

## Task 4.8 observed — the staging converge proved the three credentials nothing else touches

Dispatched via `workflow_dispatch` with `stack=main-staging`, run `34752311933`, 2026-09-13.

| Job | Result | Timing |
|---|---|---|
| `discover` | success | 10:36:55 → 10:37:00 |
| `publish` | success | 10:37:03 → 10:37:08 |
| `converge (main-staging)` | success | 10:37:12 → **10:44:24** |

**Seven and a quarter minutes is the point.** A converge that failed on a credential would fail in seconds — at the tailnet join or the first SSH attempt — so the duration is itself evidence that the play ran against a real host rather than dying at the door.

What it establishes, and why no earlier step could:

- **`TAILSCALE_OAUTH_CLIENT_ID` and `TAILSCALE_OAUTH_SECRET`** — the runner joins the tailnet with them, and the host's SSH is reachable over the tailnet and not the public internet, so a wrong value stops the job before Ansible starts.
- **`ANSIBLE_SSH_PRIVATE_KEY`** — it authenticated as `root` on the staging host. This is the value `credential-audit.md` §1.3 could only establish as *a working key from the workstation*; this establishes that the copy written into `main-staging` is that key.
- **`ANSIBLE_VAULT_PASSWORD`** — the play reads `group_vars/staging.yml`, whose vault block is `$ANSIBLE_VAULT;1.2;AES256;production`-form encrypted content. A wrong password fails the parse before any task runs.

It also attached to the right Environment and did not pause: a deployment record for `main-staging` was created at 10:37:09Z and the job started three seconds later.

**All six of `main-staging`'s secrets are now exercised** — `HCLOUD_TOKEN` and `TF_API_TOKEN` by task 4.7's apply, these three by this converge. Nothing in staging's half rests on an unverified value.

**This is why the task moved from section 8 to section 4.** Under the plan as first written, the first exercise of these three would have been production's gated deploy, on a trigger `platform-deploy.yml` offers no way to re-raise. Here the same mistake would have cost a re-dispatch.


## Section 6 — `main-production` built, and six values recovered rather than retyped

Fifteen secrets present, the name list equal to `production`'s from §1.2, and the required reviewer (`shatynska`) verified both before the writes and after them. The repository-scoped `TF_API_TOKEN` was rewritten from the same workstation file in the same pass, so the two copies *HCP Terraform Access via a Static Token, Unsplit by Privilege* (`openspec/specs/iac-state-management/spec.md`) obliges to be identical are identical by construction rather than by assumption.

**Six of the fifteen were read back off the running production stack instead of retyped**, which matters because these are among the seven that no observation in section 8 exercises. A recovered value is correct by construction; a retyped one is correct only if nobody made a mistake:

| Secret | Where it was read from |
|---|---|
| `PLATFORM_ACME_EMAIL` | `platform-traefik-1`'s command line |
| `PLATFORM_DEPLOY_HOST` | `platform-grafana-1`'s `GF_SERVER_ROOT_URL` |
| `PLATFORM_SLACK_WEBHOOK_URL` | the `slack` receiver's `api_url` in Alertmanager's rendered config |
| `PLATFORM_DEADMANSWITCH_URL` | the `deadmansswitch` receiver's webhook `url`, same file |
| `PLATFORM_GRAFANA_ADMIN_PASSWORD` | `platform-grafana-1`'s `GF_SECURITY_ADMIN_PASSWORD` |
| the Postgres trio | `platform-postgres-1`'s environment and the exporter's `DATA_SOURCE_NAME` |

### The exporter password contains an `@`, and the DSN is not URL-encoded

Worth recording because the mistake it invites is invisible. `platform-postgres-exporter-1`'s DSN reads

    postgresql://pgexporter:<password>@postgres:5432/postgres?sslmode=disable

and the password itself contains an `@`, so the string carries **two**. Splitting on the first — the obvious parse — yields a truncated password that looks entirely plausible. The correct extraction takes everything up to the **last** `@`, and it was verified by reconstructing the DSN and comparing byte-for-byte rather than by inspection.

The live value is 15 characters, contains exactly one `@`, ends `Xk4`, and its SHA-256 begins `eacaa954a403`. That fingerprint is recorded so a future operator can check a stored copy without either value being printed.

**A latent trap in the platform's Compose configuration, which is not this change's to fix**: a password embedded in a URI should be percent-encoded. This one is not, and it works only because the driver splits on the last `@`. A password containing `/` or `?` would break the DSN outright.

**Why the care is proportionate.** `PLATFORM_POSTGRES_EXPORTER_PASSWORD` is exercised by nothing in section 8: a production apply, converge and deploy all succeed with it wrong, and the symptom is Postgres metrics quietly absent from Prometheus — plausibly noticed weeks later, after this change is archived and nobody is looking at it as a cause.

## Incidental observations, recorded rather than acted on

- The tailnet machine names are `main-production` and `main-staging` — the stack names, per `docs/naming-conventions.md`'s rule that a server's name reaches the tailnet and therefore carries its stack. The hosts' own hostnames are `shatynska-main-production` and `shatynska-main-staging`, templated by the converge from the `company` group variable. Both are correct under the scheme and the divergence is deliberate; noted because reading the two side by side invites the conclusion that one of them is wrong.
- `main-staging`'s host is up and reachable, so staging is a live stack rather than a disabled one. Task 4.7's dispatched staging converge therefore has a host to converge.
