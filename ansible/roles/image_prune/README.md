# `image_prune`

Installs `/usr/local/bin/prune-host-images` and a weekly systemd timer that
runs it. The script removes every local container image that no enumerated
application and no container on this host still references.

This is the complement to the reclamation `app-deploy` performs at deploy time
(`deploy_user`), not a replacement for it. The two differ in what they may
claim authority over, not only in how often they run.

## What the keep set is

The union, over **every** application in `deploy_apps`, of the images that
application's Compose file on the host references — rendered across every
profile that file declares, not only the profiles active at the moment — unioned
with the image of **every** container on the host, running or stopped.

A single application's reference set is not authority over an image other
applications also use, which is why `app-deploy` may not consider one. The
union across every enumerated application is such an authority, and it is what
lets this remove a shared base image superseded by a newer pin — `traefik:v3.2`
against a live `v3.7.10`, `postgres:16` against a live `postgres:16.15` — that
no single deploy could touch.

References are resolved to **image identities** before comparison, so a digest
pin, a moving tag and a multiply-tagged image are each compared as the image
they are rather than as the string that names them. An image outside the keep
set is removed by each of its tags where it has tags, and by identity where it
has none. Removal is never forced: the runtime's refusal to remove an image a
container holds is the last backstop against a wrong keep set.

Age is never consulted. `docker image prune --filter until=` selects on an
image's creation timestamp, which for a pulled image is its upstream build
date, so it does not distinguish an image this host stopped using from one it
uses constantly — the running `prom/alertmanager:v0.28.1` was created in March
2025.

## `deploy_apps` — the one required input

Read from the same inventory variable `deploy_user` reads
(`ansible/inventory/group_vars/prod.yml`), **not copied into a second one**: a
divergence between two such lists would offer a live application's images for
removal.

An empty list is a supplied value, not a missing one. The role accepts it; the
script then abandons its run and reports that the enumeration names no
application, because with nothing enumerated the keep set would reduce to the
images containers currently hold — which is `docker image prune -a`, weekly,
reporting success.

## Removing an application from `deploy_apps` makes its images reclaimable

This is the operational consequence to know before editing that list.

The enumeration is written to `/etc/prune-host-images/apps` **at converge
time**, and the script reads that file rather than the host's filesystem. So an
application removed from `deploy_apps` becomes reclaimable at the next
scheduled run *after the next converge* — not at the next run.

That is deliberate. `/opt/<app>` directories are created by Ansible and never
removed by it, so a retired application leaves its directory and its last
Compose file behind indefinitely; discovering applications by globbing `/opt/*`
would let that stale file protect its images forever. Retiring an application
is removing its entry, and this is what makes that mean something.

An application cannot be deployed without being enumerated — the `sudoers` rule
and the `authorized_keys` forced command are generated from this same list — so
the list cannot silently omit something that is actually deploying.

## When a run abandons

The script removes nothing and exits **non-zero**, leaving a failed unit, when:

- the host carries no enumeration at all (it has not been converged with this
  role);
- the enumeration is present and names no application;
- an enumerated application's Compose file exists but cannot be rendered;
- rendering yields a reference that is not well formed, which is what an unset
  interpolation variable produces — `docker compose config` returns 0 on one;
- the local images or containers could not be enumerated;
- the resulting keep set is empty.

Each reports its own condition, distinguishably: an absent enumeration is
remedied by a converge and an empty one by an inventory edit, and a report
conflating them sends an operator to the wrong place.

Unlike `app-deploy`'s reclamation, which must never fail a deploy that already
succeeded, this unit has no caller to damage. It fails, so the host records it.

**Nothing scrapes the journal.** `systemctl list-units --failed` and
`HostDiskPressure` (at 90% full, which is very late) are the only signals.
Making a silently-stopped prune alertable needs node-exporter's textfile
collector and is recorded in `docs/change-queue.md`.

## Variables

| Variable | Default | Meaning |
|---|---|---|
| `deploy_apps` | *(required, no default)* | The version-controlled application enumeration |
| `image_prune_on_calendar` | `Sun *-*-* 04:00:00 UTC` | Timer schedule |
| `image_prune_randomized_delay_sec` | `3600` | Jitter, so runs do not land on a fixed minute |
| `image_prune_timeout_start_sec` | `600` | Duration bound for the whole run, enumeration included |

The bound is the unit's, not a `timeout` inside the script: systemd records the
expiry and marks the unit failed from outside the process, which is where a
report about a killed region has to come from.

## Testing

`molecule test --all` from this directory. Two scenarios: `default` for the
keep-set and removal cases, `abandon-paths` for the three abandon branches whose
arrangements `default`'s own fixtures put out of reach. Read the
`SCENARIO RECAP` rather than the exit code — scenarios run in sorted order and
stop at the first failure, so `abandon-paths` sorting first means a red one
hides `default` entirely.

Two guards are **not** covered by any assertion and are held by review and a
static read of the installed script: the pre-removal tag re-check and the
enumerate-local-images-before-keep-set ordering. Both are observable only when
the host's images change midway through a run, and a black-box scenario has no
seam at which to change them. They are also the two that close the
concurrent-deploy window. If you edit either, read them line by line — nothing
else will catch their absence.
