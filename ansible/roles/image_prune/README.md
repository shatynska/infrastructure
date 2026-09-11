# `image_prune`

Installs `/usr/local/bin/prune-host-images` and a weekly systemd timer that runs it. The script removes every local container image that no enumerated application and no container on this host still references.

This is the complement to the reclamation `app-deploy` performs at deploy time (`deploy_user`), not a replacement for it. The two differ in what they may claim authority over, not only in how often they run.

## What the keep set is

The union, over **every** application in `deploy_apps`, of the images that application's Compose file on the host references — rendered across every profile that file declares, not only the profiles active at the moment — unioned with the image of **every** container on the host, running or stopped.

A single application's reference set is not authority over an image other applications also use, which is why `app-deploy` may not consider one. The union across every enumerated application is such an authority, and it is what lets this remove a shared base image superseded by a newer pin — `traefik:v3.2` against a live `v3.7.10`, `postgres:16` against a live `postgres:16.15` — that no single deploy could touch.

References are resolved to **image identities** before comparison, so a digest pin, a moving tag and a multiply-tagged image are each compared as the image they are rather than as the string that names them. An image outside the keep set is removed by each of its tags where it has tags, and by identity where it has none. Removal is never forced: the runtime's refusal to remove an image a container holds is the last backstop against a wrong keep set.

Age is never consulted. `docker image prune --filter until=` selects on an image's creation timestamp, which for a pulled image is its upstream build date, so it does not distinguish an image this host stopped using from one it uses constantly — the running `prom/alertmanager:v0.28.1` was created in March 2025.

## `deploy_apps` — the one required input

Read from the same inventory variable `deploy_user` reads (the targeted environment's `ansible/inventory/group_vars/<environment>.yml`), **not copied into a second one**: a divergence between two such lists would offer a live application's images for removal.

An empty list is a supplied value, not a missing one. The role accepts it; the script then abandons its run and reports that the enumeration names no application, because with nothing enumerated the keep set would reduce to the images containers currently hold — which is `docker image prune -a`, weekly, reporting success.

## Removing an application from `deploy_apps` makes its images reclaimable

This is the operational consequence to know before editing that list.

The enumeration is written to `/etc/prune-host-images/apps` **at converge time**, and the script reads that file rather than the host's filesystem. So an application removed from `deploy_apps` becomes reclaimable at the next scheduled run *after the next converge* — not at the next run.

That is deliberate. `/opt/<app>` directories are created by Ansible and never removed by it, so a retired application leaves its directory and its last Compose file behind indefinitely; discovering applications by globbing `/opt/*` would let that stale file protect its images forever. Retiring an application is removing its entry, and this is what makes that mean something.

An application cannot be deployed without being enumerated — the `sudoers` rule and the `authorized_keys` forced command are generated from this same list — so the list cannot silently omit something that is actually deploying.

## When a run abandons

The script removes nothing and exits **non-zero**, leaving a failed unit, when:

- the host carries no enumeration at all (it has not been converged with this role);
- the enumeration is present and names no application;
- an enumerated application's Compose file exists but cannot be rendered;
- rendering yields a reference that is not well formed, which is what an unset interpolation variable produces — `docker compose config` returns 0 on one;
- the local images or containers could not be enumerated;
- the resulting keep set is empty.

Each reports its own condition, distinguishably: an absent enumeration is remedied by a converge and an empty one by an inventory edit, and a report conflating them sends an operator to the wrong place.

Unlike `app-deploy`'s reclamation, which must never fail a deploy that already succeeded, this unit has no caller to damage. It fails, so the host records it.

**Nothing scrapes the journal.** `systemctl list-units --failed` and `HostDiskPressure` (at 90% full, which is very late) are the only signals. Making a silently-stopped prune alertable needs node-exporter's textfile collector and is recorded in `docs/change-queue.md`.

## Liveness reporting — a silent check is the alarm, not a red unit

Every activation reports to an external observer: the unit's `ExecStopPost=` runs a `0700` script that pings this host's own check on success and that check's `/fail` endpoint otherwise. **What raises the alarm is the check going quiet**, not the ping — so a failed run, a run killed on the duration bound, and a timer that has stopped firing altogether are equally visible. The last of those is the one nothing else here can see: a timer that never fires leaves no failed unit behind, and `systemctl list-units --failed` is a manual read that nothing performs on a schedule.

The slug is `<inventory_hostname>-prune-host-images`, templated rather than written as a literal, so a second host converged by this role gets a check of its own rather than sharing this one — two hosts on one check would mean the live host's weekly success keeping it green while the other host's timer was dead.

The period and grace that decide when silence becomes an alarm are the observer's own configuration and are **not** in this repository; they are recorded in `docs/bootstrap-a-new-host.md`, Appendix A, beside the secret.

Two consequences worth knowing before editing this:

- **The report cannot fail the unit.** `ExecStopPost=` carries a `-` prefix, so a prune that did its work correctly is never recorded as failed because the observer was briefly unreachable. The undelivered ping becomes silence, which is what alarms. The attempted endpoint and `curl`'s status go to the journal, and that line is the only local trace an operator answering the silence has.
- **Removing the ping key input breaks convergence by design.** See below.

## Variables

| Variable | Default | Meaning |
|---|---|---|
| `deploy_apps` | *(required, no default)* | The version-controlled application enumeration |
| `image_prune_heartbeat_ping_key` | *(required, no default)* | The observer's project ping key, Vault-encrypted in inventory. A scheduled unit running unobserved is the state this reporting exists to end, so an absent key is refused rather than tolerated |
| `image_prune_heartbeat_base_url` | `https://hc-ping.com` | The observer's base URL. A variable rather than a literal so a Molecule scenario can point the reporter at a local sink; every scenario this role has sets it, and `.github/tests` asserts that over all of them |
| `image_prune_on_calendar` | `Sun *-*-* 04:00:00 UTC` | Timer schedule |
| `image_prune_randomized_delay_sec` | `3600` | Jitter, so runs do not land on a fixed minute |
| `image_prune_timeout_start_sec` | `600` | Duration bound for the whole run, enumeration included |
| `image_prune_apt_cache_valid_time` | `3600` | Seconds an already-fetched package index may be reused for, when installing this role's HTTP client. **May save nothing on a host carrying a maintained `apt` update-success stamp** — see `defaults/main.yml`. |

The bound is the unit's, not a `timeout` inside the script: systemd records the expiry and marks the unit failed from outside the process, which is where a report about a killed region has to come from.

## Testing

`molecule test --all` from this directory. Four scenarios: `default` for the keep-set and removal cases, `abandon-paths` for the three abandon branches whose arrangements `default`'s own fixtures put out of reach, `heartbeat` for what a successful, a failing and a killed activation report, and `absent-heartbeat-key` for the role refusing to converge when the ping key is not supplied. Read the `SCENARIO RECAP` rather than the exit code — scenarios run in sorted order and stop at the first failure, so `abandon-paths` sorting first means a red one hides the other three entirely.

No scenario reaches the external observer: each one points `image_prune_heartbeat_base_url` at a local address, and `heartbeat` starts a sink there to read what arrived. That is not tidiness — left on the production default, a scenario would create a check at the observer from a hosted runner on every pull request touching `ansible/`.

Two guards are **not** covered by any assertion and are held by review and a static read of the installed script: the pre-removal tag re-check and the enumerate-local-images-before-keep-set ordering. Both are observable only when the host's images change midway through a run, and a black-box scenario has no seam at which to change them. They are also the two that close the concurrent-deploy window. If you edit either, read them line by line — nothing else will catch their absence.
