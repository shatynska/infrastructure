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

**Not captured by me:** the two heartbeat checks' period and grace at the observer. That read needs the observer's own account, which this session has no credential for; it is the operator's, and the runbook's phase 1 calls for it. **Until it is done, phase 12's comparison has nothing to compare against beyond what the register claims.**

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
