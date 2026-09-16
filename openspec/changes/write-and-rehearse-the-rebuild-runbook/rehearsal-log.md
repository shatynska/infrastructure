# Rehearsal log — `main-staging`

The running record of the rehearsal the runbook calls for. Timings and divergences are written here as each phase completes, rather than at the end, so an interrupted run still leaves an account of how far it got. What belongs in the document itself — corrections to steps, and the finished record — is moved there at task 7.1 and 7.2; this file is archived with the change.

**Stack:** `main-staging`. **Route:** the `server_enabled` toggle. **Runbook followed:** `docs/runbook-rebuild.md` as merged at `54784a6` (PR #242).

## Phase 1 — pre-state, 2026-09-16T19:28:49Z

Captured by following the merged phase 1. Everything below is what "serving what it served before" means for this host, and is what phase 16 is checked against.

**Containers — ten, all up, eight of them the platform stack:**

    commerce-ops-worker-1          Up 3 hours
    commerce-ops-app-1             Up 3 hours (healthy)
    platform-postgres-1            Up 8 hours (healthy)
    platform-alertmanager-1        Up 10 hours (healthy)
    platform-grafana-1             Up 10 hours (healthy)
    platform-postgres-exporter-1   Up 10 hours (healthy)
    platform-traefik-1             Up 10 hours (healthy)
    platform-cadvisor-1            Up 10 hours (healthy)
    platform-prometheus-1          Up 10 hours (healthy)
    platform-node-exporter-1       Up 10 hours (healthy)

`platform-postgres-1`'s shorter uptime is `move-the-shared-database-onto-the-data-volume`, archived earlier today, and is not a fault.

**Scrape targets — five, all `up`:** `cadvisor`, `node-exporter`, `postgres-exporter`, `prometheus`, `traefik`.

**Addresses:** public IPv4 `62.238.17.177`; tailnet `100.85.219.36`, which `~/.ssh/config` pins as `HostName` for the `shatynska-main-staging` alias. Server type `cx23`.

**Volume:** `scsi-0HC_Volume_106839043` → `/dev/sdb`, mounted at `/mnt/main`, 9.8G with 708M used.

**Names resolving to this server**, all by the wildcard: `commerce-ops.main-staging.fincci.bike`, `main-staging.fincci.bike`, `grafana.main-staging.fincci.bike` — each `62.238.17.177`. Grafana's name resolving is not evidence that anything serves it: Grafana binds to the tailnet address alone.

**Serving:** `https://commerce-ops.main-staging.fincci.bike/` answers **404**, `/health` and `/docs` answer **200**. See the divergence below — the 404 is the application's and is the healthy state.

**The observer read, performed by the operator at ~19:45Z — before the destroy, which is the only point at which it means anything.** This session holds no credential for the observer, so it was asked for and reported back. What it found:

| Check | Appendix A recorded | The observer carried |
|---|---|---|
| `main-production-alertmanager` | 5 minutes / 5 minutes | 5 minutes / **2 minutes** |
| `main-staging-alertmanager` | 5 minutes / 5 minutes | **did not exist** |
| `main-staging-prune-host-images` | 7 days / 2 days | 7 days / **2 hours** |

**The timing is what makes this usable, and it is the distinction phase 12 turns on.** A disagreement found *before* the destroy is between two claims about a running system, and the register is the one that can be wrong. A disagreement found *after* it is most likely the rebuild having reset a check to the vendor's default, and there the register is right and the observer is what you correct. These readings are the first kind, which is why Appendix A is corrected against them rather than the other way round.

The middle row is not a drift but an absence, and it is what `give-staging-its-own-dead-mans-switch-check` was opened and closed on.

### Divergences found in phase 1

1. **The serving check is wrong, and wrong in the direction that hides a real failure.** Phase 1 and phase 16 both run `curl -sS -o /dev/null -w '%{http_code}\n' https://commerce-ops.main-staging.fincci.bike`, written as though a good answer were `200`. The application answers **404** at `/` by design — it is a FastAPI service with no route there — so an operator reading the runbook literally would record a failure before touching anything, or, worse, read a 404 *after* the rebuild as the expected state.

   **It hides a real failure because Traefik's own 404 is indistinguishable by status code.** A router that never matched — because DNS is stale, or the certificate did not issue, or the application's labels did not come back — answers 404 as well. The discriminator is the `server:` header and the body's content type: the application answers `server: uvicorn` with `application/json`, Traefik answers its own. The correction is to probe `/health` (200) and to say what a bare 404 does and does not prove.

2. **`dig` is not installed on this workstation**, so a reader checking which names resolve has to reach for something else. Not a runbook defect — it names no such command — but phase 5's instruction to read the zone at the provider is the only resolution step it gives, and a local check is worth having. `python3 -c 'import socket; print(socket.gethostbyname(...))'` is what was used here.

3. **Phase 1's own credential line is short by one.** It names the operator inspection key, `gh`'s token and the read-only Hetzner token. The capture also needs the **heartbeat observer's account**, for the period-and-grace read the same phase asks for — which is the one part of phase 1 this session could not perform.

## Phase 3 — the destroy plan, read before merging, 2026-09-16T19:35Z

The plan job of PR #243 (`server_enabled = false` on `main-staging`), read from the pull request's own plan comment. **Nothing has been applied**; this is the plan alone.

    Plan: 0 to add, 0 to change, 3 to destroy.

      # module.server[0].hcloud_firewall.this will be destroyed
      # module.server[0].hcloud_server.this   will be destroyed
      # module.volume[0].hcloud_volume.this   will be destroyed

    hcloud_ssh_key.this: Refreshing state... [id=118598421]
    module.volume[0].hcloud_volume.this: Refreshing state... [id=106839043]

**This is the first live observation of the volume/server coupling**, which `docs/backlog.md` `exercise-the-volume-server-coupling-against-live-state` records as never exercised. It confirms three things and disproves one:

- The toggle destroys the **server, its firewall and the volume together**, exactly as `main.tf`'s `count = var.volume_enabled && var.server_enabled ? 1 : 0` says it must.
- `hcloud_ssh_key.this` is **refreshed and not destroyed** — it is stack-owned and ungated, and outlives the server as its own file's comment intends.
- The volume id is `106839043`, matching the `scsi-0HC_Volume_106839043` the phase 1 capture read from the host. The two reads agree, which is what makes either of them worth anything.
- **`docs/bootstrap-a-new-host.md`'s Appendix B was wrong of this route**, as the change proposed: staging's data volume *is* wiped by a rebuild performed by the toggle. The runbook's phase 3 states the scoped version and is confirmed by this plan.

**The observation cost no destruction.** It is a plan against live state, which is precisely the shape `exercise-the-volume-server-coupling-against-live-state` asks for and could not find a home for — that entry says a local plan cannot be run because the workstation's HCP credential belongs to another organisation, and concludes that "whoever takes this either obtains an HCP credential for this organisation, or finds the reads a home in the pipeline". **The pull-request plan job is that home**, and it was available all along. The entry's remaining half is production's own coupling, which this does not touch.

### Divergence found in phase 3

4. **The destroy pull request's checks can fail transiently, and the runbook does not say so.** `validate` failed on its first run with `could not connect to registry.terraform.io: ... read: connection reset by peer`, while initialising the **`main-production`** stack — a stack the pull request does not touch. `plan (main-staging)` had already passed. A re-run of the failed job was the whole remedy.

   It matters here more than it would elsewhere: this is the pull request whose merge destroys a host, so an operator meeting a red check on it is in exactly the state where reading it as "something about my change is wrong" costs the most. The runbook's phase 3 should say that the check aggregates every stack, that a failure naming a stack the change does not touch is usually the registry rather than the change, and that the remedy is a re-run rather than an edit.

## Interlude — three defects found before the destroy, two fixed, 2026-09-16T20:00–20:30Z

The pre-state capture found more than it was looking for, and the fixes were taken before the rebuild rather than after, because two of them bear on what the rebuild can observe.

**What was found, all by reading the running hosts rather than the documents:**

- Both hosts pinged one dead-man's-switch check, so production's liveness alarm was masked — a single check fed by two hosts stays green while either is alive.
- Both hosts posted alerts through one webhook, into one channel, in one Slack workspace — and it was the **staging** workspace, so production's alerts had never reached the Slack its operator watches. Confirmed by delivery: two probes, both arriving in staging's `#alerts`, none in production's.
- Both hosts hold one Grafana admin password. Not fixed; it needs no container change and was left out to keep the urgent fix small.
- A **rotated secret does not reach its container on a deploy.** Measured: staging's ping URL replaced at 19:45:05Z, deploy green at 19:45:23Z, the container still up eleven hours afterwards on the old value. The `platform.config-checksum` label is computed from the committed config text, and a secret is not in that text.

**What was done.** PR #244 edited the config block, which moved the checksum, which recreated the container — using the mechanism as designed rather than working around it, and recording at the point of use why a rotation needs it. After the deploy: both Alertmanagers recreated (44 seconds and one minute old), the Slack workspace ids distinct, the ping URLs distinct, and a probe from each host arriving in its own workspace and in neither other. **That is `docs/bootstrap-a-new-host.md` §7.5's check, performed for the first time since the system was built, and passing.**

**Why it belongs in this log.** None of it is the rebuild, and all of it is the rehearsal: every one of these is a per-stack GitHub Environment secret, which no committed file can see, so no test in this repository and no reviewer could have reached any of them. The only mechanism that does is an operator comparing two running hosts — which is the class of step the runbook exists to make someone actually perform.

## Phase 3 applied — the destroy, 2026-09-16T20:20:30Z → 20:21:42Z

**72 seconds**, merge to `Apply complete`. Unattended: no reviewer on that Environment, no `destroy-override` label, exactly as the runbook says of this stack.

    module.volume[0].hcloud_volume.this:   Destruction complete after 9s
    module.server[0].hcloud_server.this:   Destruction complete after 16s
    module.server[0].hcloud_firewall.this: Destruction complete after 1s

    Apply complete! Resources: 0 added, 0 changed, 3 destroyed.

Confirmed from outside rather than from the green: `ssh` to the tailnet address times out, and `https://commerce-ops.main-staging.fincci.bike` returns `000`.

**The volume is destroyed first, not last.** The plan said the three go together and the apply says the volume goes *before* the server it is attached to. That is a stronger statement than the coupling as documented — which is about the volume being unable to exist without the server — and it is the detail a reader planning around "detach the volume and keep it" would need. Nothing in this repository said it, because nothing had run it.

## Phase 4 — the recreate, opened 2026-09-16T20:23Z

PR #245. Waiting on the operator's merge.

### Running timings

| Phase | Wall clock |
|---|---|
| 1 — pre-state capture | ~9 min, including the three defects it surfaced |
| *interlude* — alert-routing defects found and fixed | ~30 min, not part of the sequence |
| 3 — destroy, merge to apply complete | 1 min 12 s |

## Phase 4 applied — the recreate, 2026-09-16T20:27:12Z → 20:28:32Z

**82 seconds**, merge to `Apply complete`.

    module.server[0].hcloud_firewall.this: Creation complete after 1s  [id=11635130]
    module.server[0].hcloud_server.this:   Creation complete after 18s [id=166213892]
    module.volume[0].hcloud_volume.this:   Creation complete after 18s [id=106886751]

    Apply complete! Resources: 3 added, 0 changed, 0 destroyed.

Read back from the inventory, as the runbook says rather than from `terraform output`: server id **166213892** (was 165402032), volume id **106886751** (was 106839043), status `running`, reachable as `root` on the public address within nine minutes of creation.

### Divergences found in phase 4

5. **The public IPv4 did not change, and the runbook assumes it always does.** It is `62.238.17.177` before and after — the same address, on a different server. Hetzner handed it back, presumably because the destroy and the create were seven minutes apart and the address was still held for that project. So **phase 5's DNS step was a no-op this time**, and every record aimed at this host was already correct.

   The correction is not "the address does not change" — that is the same error in the other direction, and a slower rebuild would very likely get a different one. It is that the step is **conditional and the condition must be checked rather than assumed**: read the address back, compare it with what phase 1 recorded, and edit DNS only if it moved. As written, phase 5 sends an operator to a DNS provider to re-enter a value that is already right, which is a step that can only introduce an error.

6. **The stale `known_hosts` entry bit at the public address after all — and an earlier correction to this runbook made that harder to see.** Code review found the warning sitting beside the new-public-IP connection and moved it to phase 8's reused tailnet name, on the reasoning that a brand-new address carries no stale entry. That reasoning is sound and its premise was false here: the address was **reused**, so `ssh root@62.238.17.177` failed with `REMOTE HOST IDENTIFICATION HAS CHANGED!` and `ssh-keygen -F` confirms the stale entry was present.

   The honest statement covers both and neither location alone: the entry bites at **any address or name you have connected to before**, and after a quick rebuild the public address may well be one of them. Both phase 7 and phase 8 need it, with `ssh-keygen -R` given for each.

   Worth recording as a process note rather than only as a text fix: this is a correction that was **reviewed, agreed, and wrong**, and nothing but running the sequence would have caught it. The reviewer reasoned from what a rebuild usually does; the rehearsal observed what this one did.

### Running timings

| Phase | Wall clock |
|---|---|
| 3 — destroy, merge to apply complete | 1 min 12 s |
| 4 — recreate, merge to apply complete | 1 min 22 s |
| 5 — DNS | **not needed** — the address was reused |

## Phase 12 — the observer, confirmed 2026-09-16T~21:20Z

Both of this stack's checks confirmed green by the operator. **The two are not equally well evidenced and the difference is worth keeping.**

`main-staging-prune-host-images` was read before the destroy and read again after, on the same settings — so of that check it can be said that **the rebuild reset nothing**, which is the failure this phase exists to catch. The prune reporter's `OK` rather than `Created` at 21:10 says the same thing from the host's side: `create=1` would have brought a new check into existence on the observer's default.

`main-staging-alertmanager` cannot be spoken of that way, because at the pre-destroy read **it did not exist** — both hosts were feeding production's check. It was created that evening by its own first ping, after the fix, which means it came into existence carrying the vendor's default until someone set it. It is green; its period and grace at the observer have not been read. **That read is still owed**, and Appendix A's row for it is set from production's observation rather than from its own.

So the register is corrected against the **pre-destroy** reading, and the post-rebuild reading is what establishes that the rebuild changed nothing to correct against.

**The evidence for the prune's grace**, gathered on the host and recorded here because Appendix A now cites it: `ansible/roles/image_prune/defaults/main.yml` declares `image_prune_on_calendar: "Sun *-*-* 04:00:00 UTC"` and `image_prune_randomized_delay_sec: 3600`, and `systemctl list-timers prune-host-images.timer` on the pre-rebuild host showed `LAST Sun 2026-09-13 04:28:03 UTC` and `NEXT Sun 2026-09-20 04:34:12 UTC` — both inside the hour the jitter bounds. That is what makes two hours a tolerance and two days a blind spot.

### Divergence found before phase 7

7. **The runbook speaks of "the" Tailscale auth key; this deployment has one per stack.** Phase 2 says to check "the reusable auth key", following `docs/bootstrap-a-new-host.md` §5.3, which records that one reusable key serves both hosts. The tailnet here holds **two** auth keys, and the operator could not tell which was wanted — they are distinguished only by their description, one of which names staging.

   That is not a defect in the deployment: §5.3 permits a second key outright, for the reason this one exists — *"if you want to revoke one host's join without touching the other."* It is a gap in the runbook, which assumes the documented default and gives a reader with the permitted variant nothing to choose by. Phase 2 should name the description as the discriminator, and say that a fresh key is the cheap answer when it is unclear — a single-use key is burnt by the first join, so a rebuilt host needs one anyway.

   Cost: a few minutes of the operator's time, at a phase whose entire purpose is to prevent exactly that later.

### Phase 7, first attempt — failed at inventory parse, 2026-09-16T~20:55Z

    Invalid Hetzner Cloud API Token: unable to authenticate (unauthorized)
    [ERROR]: Completely failed to parse inventory source .../main-staging.hcloud.yml

`direnv` was not active in the operator's shell, so `HCLOUD_TOKEN_MAIN_STAGING` was unset. Nothing reached the host; the run failed before connecting.

**This is the runbook working, not failing.** Phase 2's first command is that same inventory read, placed there so this surfaces before a converge is half-done. The operator went from phase 5 straight to phase 7 and met it there instead — which is the evidence that phase 2 earns its place rather than being a formality.

**It is also `ansible.cfg`'s `any_unparsed_is_failed` earning its place.** Without it the source would have resolved to a group with no host in it and the play would have reported success having converged nothing — byte-identical to a host that was destroyed, which is precisely the state this host was in twenty minutes earlier. The clean failure naming the source is that setting's whole purpose, observed.

### Divergence found in phase 7

8. **Neither phase 2 nor phase 7 says how the token gets into the shell.** Phase 2 runs the inventory read and says a failure "names the source it could not parse", and phase 7 gives the `ansible-playbook` line — but neither mentions `direnv allow` or `source .envrc`, and `ansible/.envrc` is **per working tree**, so a tree cloned since the last rebuild has no token at all however well the main checkout is provisioned. Phase 1's credential line was corrected to say that during code review; phases 2 and 7, which are where it is actually used, were not.

   The fix is one clause in phase 2: the read is run after `direnv allow` in `ansible/`, or after `source .envrc`, and the failure above is what an unprovisioned shell looks like.

## Phase 7 applied — the workstation converge, 2026-09-16T~20:58Z

    localhost      : ok=2    changed=0   unreachable=0 failed=0
    main-staging   : ok=100  changed=56  unreachable=0 failed=0

Verified on the host afterwards: `hostname` is `shatynska-main-staging`; `/mnt/main` is mounted on the new volume `scsi-0HC_Volume_106886751` and is empty (2.1M of 9.8G used, which is the volume loss made visible); `prune-host-images.timer` exists and is scheduled.

**The tailnet address changed: `100.85.219.36` → `100.95.46.64`.** So the rebuild moved the tailnet address and did *not* move the public one — the opposite of what the runbook expects, in both halves.

## Phase 8 — the converge key, 2026-09-16T20:59Z

### Divergence found in phase 8 — the phase's own command is broken as written

9. **`ssh-copy-id -i …pub` fails for the operator who followed the bootstrap's instruction.** It refuses with `ERROR: failed to open ID file '…/shatynska-ansible-ci-main-staging': No such file`, because it wants the **private** half to verify the pair even when handed the public one. `-f` is what skips that check, and the error names it.

   This is the second half of a defect whose first half code review found and I mis-answered. Review established that the phase's *verification* step needed a private half that stage 0.3 has the operator delete; the fix replaced that step with a pipeline dispatch, and I wrote — in the report and in the correction — that *"`ssh-copy-id` is unaffected; it uses the `.pub`, which survives."* **That is false**, and it was reasoned rather than run. The phase's very first command fails for exactly the reader the rest of the phase was corrected to serve.

   The fix is one character: `ssh-copy-id -f -i ~/.ssh/<key>.pub …`. Confirmed working here — the key installed and the pipeline dispatch that follows is what proves it usable.

   Worth keeping as the clearest case the rehearsal produced. A defect was found by review, correctly. The correction was reviewed and agreed. The correction was still wrong, in a way only running it could show, and it was wrong in the same place and for the same underlying reason as the original.

## Phase 8 confirmed, phase 9 and 10 — 2026-09-16T20:59Z–21:07Z

**Phase 8's dispatch went green**, which is what proves the converge key usable: it is the Environment secret's copy that the pipeline reads, and the only copy that exists.

**Phase 9 — three holders of the tailnet address, and it moved.** `100.85.219.36` → `100.95.46.64`. Updated: `PLATFORM_DEPLOY_HOST` on the `main-staging` Environment, `DEPLOY_HOST` on `commerce-ops`'s `staging` Environment, and `~/.ssh/config`'s alias. The third is the one nothing would have reminded anyone about, and the runbook names it because code review found it missing.

**Phase 10 — all eight platform containers up and healthy within seconds of the deploy.**

### Divergence found across phases 7, 8 and 10 — the host key bites in *three* places, not one

10. The rebuilt host presents a new host key on **every** identity it is reached by, and the runbook treats this as one note in one phase. Observed, in order:

    - `root@62.238.17.177` — the **public address**, reused by Hetzner, so the stale entry was present. `REMOTE HOST IDENTIFICATION HAS CHANGED!`
    - `root@main-staging` — the **tailnet name**, at phase 8's `ssh-copy-id`.
    - `shatynska-main-staging` — the `~/.ssh/config` **alias**, which resolves to the tailnet *address*. Accepting the key under the name does **not** record it for the address, so this failed separately, after the other two were already cleared: `Host key verification failed` and an `ssh_askpass` error in a non-interactive shell.

    Three surfaces, three separate `ssh-keygen -R`, and each one only appears when that identity is first used — spread across three phases. The runbook should say that once, early, with all three named: the public address, the tailnet name, and the tailnet address behind any local alias.

### Divergence found in phase 11 — it does not need the password manager at all

11. **`platform/README.md` has the operator type `PLATFORM_POSTGRES_EXPORTER_PASSWORD` into `psql`, and the value is already on the host.** The `postgres-exporter` container is running with it as `DATA_SOURCE_PASS`, rendered from that stack's Environment secret at deploy time — which is the authoritative copy, being exactly what the exporter will present when it connects.

    So the role can be created from the value the container already holds, on the host, without the secret being fetched from a password manager, pasted into a shell, or appearing in any history. That is the same act with fewer places to leak it or mistype it, and it removes the phase's only dependency on a credential the operator has to go and find.

    It is worth saying what it does *not* remove: the value still has to be correct in the Environment, and if it is wrong there the exporter and the role will agree with each other and both be wrong. The check is unchanged — `pg_up 1` and `pg_exporter_last_scrape_error 0`.

## Phases 11, 13, 14 applied — 2026-09-16T21:08Z–21:11Z

- **11** — `pgexporter` role created from the value the exporter container already held. `CREATE ROLE`, `GRANT ROLE`, then `pg_up 1` and `pg_exporter_last_scrape_error 0`. All five scrape targets `up`, matching the phase 1 capture exactly.
- **13** — one prune activation: `considered 8, removed 0, refused 0`, and the reporter answered **`OK`** rather than `Created`, which says the heartbeat check **survived the rebuild** rather than being re-created on the observer's default. N=8 is the platform stack alone, since the application had not redeployed yet — the documented expectation.
- **14** — the re-provisioning recipe with `rotate=yes`, output exactly as `docs/onboard-an-application.md` §3.2 describes: four `SET`s, `CREATE ROLE`, `CREATE DATABASE`, `REVOKE`. Confirmed afterwards: database `commerce-ops` owned by role `commerce-ops`, Environment secret rotated at 21:10:59Z.

## Phase 15 — the application's own deploy

### Divergence found in phase 15 — the phase assumes a button that does not exist

12. **The runbook says to "go to that application's own Actions and run its deploy for this target". `commerce-ops`'s `Deploy` workflow triggers on `push` to `main` and declares no `workflow_dispatch`**, so there is no Run workflow button and the instruction cannot be followed as written. The operator looked for it and could not find it, which is how this was found.

    The routes that do exist are re-running the last `Deploy` run, or pushing to that repository's `main`. Re-running is the one that belongs in a rebuild: it redeploys the commit already on `main` rather than requiring a commit invented to trigger a deploy. The runbook should say so, and should say that an application may offer neither a dispatch nor a re-run worth having — in which case the step is that application's own to define, and the runbook can only name the obligation.

### Divergence found across the whole window — the rebuild breaks other repositories' deploys, silently to us

13. **Two `commerce-ops` deploys failed during the rebuild window, and nothing in this repository would have told us.** Runs at 20:36 and 20:44, both failing at `Connect to the tailnet` with `❌ Ping host *** did not respond` — the host was destroyed at 20:21 and did not rejoin the tailnet until the converge at ~20:58, and `DEPLOY_HOST` still held the old address until 21:04.

    The runbook warns the operator about alarms the rebuild raises on **this** repository's checks. It says nothing about the deploys of **other** repositories that target the host, which fail for the length of the window and land in those repositories' own histories as red runs with a cause that reads as a network fault.

    Phase 1 should say to tell whoever owns each application that the window is open, for the same reason it says to announce the expected alarms — and phase 15 should note that a failed deploy from during the window is expected and is what the redeploy replaces. `docs/backlog.md` `announce-a-rebuild-to-the-applications-that-hold-databases` is the mechanised version of this and remains open; the runbook step is prose addressed to a human, which is what exists today.

## Phase 16 — the host is serving what it served before, 2026-09-16T21:18Z

Checked against the phase 1 capture, item by item, rather than against what looked reasonable:

| | Before | After |
|---|---|---|
| Containers | 10 — 8 platform, 2 application | 10, the same set, all healthy |
| Scrape targets | 5, all `up` | 5, all `up` |
| `/` on the application | 404 from `server: uvicorn` | 404 from `server: uvicorn` |
| `/health` | 200 | 200 |
| TLS | issued | reissued, Let's Encrypt |
| `pg_up` | 1 | 1 |
| Sessions on `commerce-ops` | 7 | 6 |
| Prune | — | `considered 9, removed 0, refused 0` |

`considered 9` is the closing confirmation: eight platform services plus the application's own image, which is what `docs/bootstrap-a-new-host.md` §6.5 says N should equal. At 21:10, before the application redeployed, it was 8 — the count moved by exactly the one image the redeploy added.

**The application's database is empty and that is the rebuild working.** The shared instance went with the volume, phase 14 recreated the role and database, and the application migrated into a fresh schema. Six sessions on it means it authenticated with the password phase 14 rotated.

## Timings

From the merge that destroyed the server to the confirmation that the host was serving again: **57 minutes**.

| Phase | Wall clock |
|---|---|
| 1 — pre-state capture | ~9 min |
| 2 — credential confirmation | folded into 7, and skipped, which is divergence 8 |
| 3 — destroy, merge to apply complete | **1 min 12 s** |
| 4 — recreate, merge to apply complete | **1 min 22 s** |
| 5 — DNS | **0** — the public address was reused |
| 6 — delete the dead tailnet peer | ~2 min, operator |
| 7 — workstation converge | ~8 min including one failed start at inventory parse |
| 8 — converge key and its pipeline proof | ~7 min, most of it the dispatch running |
| 9 — the three address holders | ~1 min |
| 10 — platform deploy | ~2 min |
| 11 — `pgexporter` role | <1 min |
| 12 — the observer | ~2 min, operator; the pre-destroy read is in phase 1 |
| 13 — prune activation | <1 min |
| 14 — database re-provisioning | <1 min |
| 15 — the application's own deploy | ~4 min, after the button it names was found not to exist |
| 16 — confirmation | ~2 min |

**What the number does and does not say.** Fifty-seven minutes is this operator, on this stack, with the sequence written down in front of them and someone driving it who had read every file it touches. It is not the number for an unrehearsed rebuild at three in the morning, and it is emphatically not production's — production has a reviewer on both applies, a destroy-override label, delete protection to clear first, and an application whose durable data no backup covers.

**The honest headline is the other number.** The sequence cost 57 minutes. The defects it exposed — three live ones found before anything was destroyed, and thirteen divergences in a document that had been through four rounds of plan review and three of code review — cost the rest of the evening. That is the argument for rehearsing rather than writing, and it is the argument this change was proposing on paper six hours ago.
