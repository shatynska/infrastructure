## Context

`app-deploy` reclaims, on each deploy, the images in *that* application's own `ghcr.io/<owner>/<app>` namespace that its Compose file no longer references. That mechanism shipped on 2026-09-07 and works: the host carries exactly one `ghcr.io/fuperia-it/commerce-ops` image today against 190 before it.

Its scope is a deliberate floor, not an oversight. A single application's reference set is not authority over an image other applications also use, so `app-deploy` may not consider one — and a deploy that will never happen again cannot revisit anything.

This change is the complement queue entry 10 anticipated. Everything below is about what a host-level mechanism may safely remove that a per-deploy one may not, and why the blunt form both that entry and the previous change's Alternatives section name turns out to be the wrong instrument.

## Decisions

### There is no usable retention window, so there is none

Both prior documents specify this change as `docker image prune -af --filter until=168h`. The `until` filter does not mean what that phrasing assumes.

`docker image prune --filter until=<timestamp>` removes images **created** before that timestamp, and an image's `Created` field is set by whoever built it. For anything pulled from a registry that is the *upstream build date*, not the date this host pulled it and not the date anything last used it. There is no last-used filter for images; the one Docker offers is on build cache.

Checked on the host on 2026-09-07, with `docker image inspect -f '{{.Created}}'`:

| Image | Created | State on host |
|---|---|---|
| `prom/alertmanager:v0.28.1` | 2025-03-07 | **running** |
| `postgres:16-alpine` | 2026-08-13 | **running** |
| `traefik:v3.7.10` | 2026-07-31 | **running** |
| `alpine:3.20` | 2026-04-16 | unused |

Every one of them is already outside a 168h window, including the three that are in active use. So `--filter until=168h` excludes nothing that matters, and `prune -af --filter until=168h` reduces, in fact, to `prune -af`: *remove every image no container currently holds*.

That is a live claim about a moment, not about what the host wants. The classes it loses are the ones with no container object at all: a service behind an inactive profile, a service never started, a service scaled to zero, and an application brought `down` rather than stopped. (An application merely `stop`ped keeps its containers and would survive even `prune -a` — the previous design's phrasing was loose here, and the loose half is not the case that matters.) The previous design named this breadth and called it "a broader claim than intended"; it accepted the claim only because it believed a timer bought a retention window in exchange. It does not.

A window is therefore not weakened here, it is **absent**: an image is kept because something wants it, or it is removed. Age is not consulted at all, and no part of this design may be read as bounded by one.

### The keep set is the union across every enumerated application

What one application cannot say about a shared image, all of them together can.

The keep set is the union, over every application in `deploy_apps`, of the images that application's Compose file references, unioned with the image every container on the host holds. `postgres:16-alpine` is kept because `commerce-ops` references it; `postgres:16.15` because `platform` does; `postgres:16` is removed because, after that union, nothing does.

This is the whole reason the change exists as a distinct mechanism rather than as a longer timer on the same one. The difference from `app-deploy` is not the trigger and not the bluntness — it is that the union is *authority* over a shared base image in a way a single reference set is not.

Two properties follow, and both are improvements on `prune -af` rather than concessions:

- A service that is **defined and not running** keeps its image, because the Compose file names it. That is the case `prune -af` loses.
- An image nothing references but a **stopped container** holds is kept twice over: by the container's own entry in the keep set, and by the runtime's refusal to remove it.

### An application's reference set spans every profile its file declares

The first of those properties does not hold for the naive reading of "what the Compose file names", and the gap runs exactly along the case that justifies the whole design.

`docker compose config --images` renders the file under the profiles *active at the moment it runs*, and omits every service gated behind an inactive one. Executed against Compose v5.4.0 locally; the host runs v5.5.0, where `config --profiles` was confirmed present but this behaviour was not itself re-executed:

```
services:
  always: { image: alpine:3.20 }
  gated:  { profiles: ["debug"], image: busybox:1.36 }
```

`docker compose config --images` emits `alpine:3.20` alone; with `--profile debug` it emits both. So a reference set taken from a single default rendering is short by precisely the services that are defined and never started — which is the class this union exists to protect, and the class `prune -af` was rejected for losing. Taking it naively would have reproduced that failure while claiming to have fixed it.

The reference set is therefore rendered across every profile the file declares: `docker compose config --profiles` enumerates them, and the render passes all of them. Passing a profile a file does not declare is tolerated (exit 0, checked), so the enumeration need not be exact for the render to be safe.

### The enumeration reaches the host as a file Ansible writes, not as an interpolated script

The script runs weekly, long after the converge, so the application list has to exist on the host. It cannot be interpolated into the script body: that body is wrapped in `{% raw %}…{% endraw %}` because it contains Go template syntax (`docker images --format '{{.ID}}'`) that Ansible's Jinja rendering would otherwise evaluate, and a raw block interpolates nothing.

Resolving that by wrapping only parts of the body would leave a script that is half Jinja and half Go template, in a `copy:` `content:` block, which is the collision the raw wrapper exists to avoid rather than a way around it.

Ansible therefore templates a separate data file — one application name per line — and the script, entirely raw, reads it. The consequence to state plainly is that the on-host list is only as current as the last converge: an application removed from `deploy_apps` becomes reclaimable at the next run *after* the next converge, not at the next run. That is the honest phrasing for the role's README, and it is not a defect — the same is already true of the `sudoers` rules and forced commands generated from the same list.

### The application list comes from `deploy_apps`, never from a glob of `/opt`

`/opt/<app>` directories are created by Ansible and never removed by it, so a retired application leaves its directory and its last Compose file behind indefinitely. Globbing `/opt/*/docker-compose.yml` would let that stale file go on protecting the retired application's images forever — which is precisely entry 10's third target, preserved rather than reached.

`deploy_apps` is the enumeration the repository already keeps, and `iac-host-configuration` already requires the deployable set to be enumerated in version control rather than accepted as input. Retiring an application is removing its entry, and that is what makes its images reclaimable here. The list is read from the same inventory variable `deploy_user` reads, not copied into a second one: a divergence between two such lists would delete a live application's images, which is the worst outcome this design has.

### An empty enumeration abandons the run rather than narrowing the keep set

`deploy_apps` may legitimately be an empty list — it is a supplied value, not a missing one, and the role's required-input assertion must not reject it.

What it must not do is fall through. With no application enumerated the union reduces to the images containers currently hold, and that is not a degraded version of this design — it is *exactly* `docker image prune -a`, the mechanism rejected above, running weekly and reporting a healthy completed run. The empty-keep-set guard does not catch it either, since any host with containers has a non-empty union.

"No application enumerated" is therefore its own abandon condition, reported and failing, alongside the empty keep set rather than folded into it. So is an enumeration the host does not carry at all — a host configured before this role ever ran, or one whose file was removed — which is the same refusal but a different remedy, and reporting them alike would send an operator to the inventory when the host merely needs a converge.

The consequence is worth naming: a host carrying no applications would fail this unit every week, and `iac-cicd-pipeline` records this repository's own finding that a persistently red scheduled job gets muted in practice — which would erode the failed-unit signal this design leans on.

The role is nonetheless applied unconditionally, because an enumerated-empty host is a misconfiguration rather than a state worth serving: this host runs two applications, and one carrying none has no reason to have had `host-baseline.yml` applied to it. Reporting that by failing is the intended behaviour, and making the role conditional would add a branch for a state that does not occur. If such a host ever does exist, the answer is to stop applying the role to it, not to soften the guard.

### A missing Compose file, an unresolvable one, and a malformed reference

These are three states, and collapsing any two of them removes live images.

An enumerated application with **no** `/opt/<app>/docker-compose.yml` has never deployed, so it has no images on this host either. It contributes nothing to the keep set, and skipping it is safe because there is nothing of its to remove.

An application whose Compose file **exists but cannot be rendered** — a syntax error, a Compose plugin that rejects what `up` tolerated — has its images on the host and its reference set unknown, so continuing would offer every one of them for removal. That abandons the **whole run**, not that application's contribution: a partial union is a wrong union, and a wrong union removes live images.

The third is the one that hides. `docker compose config` does **not** fail on an unset interpolation variable: it warns, substitutes the empty string, and exits 0. Checked locally — a service whose image is `ghcr.io/example/${MISSING}:v1` renders as `ghcr.io/example/:v1`, with a warning on stderr and status 0. Since `.env` is delivered to `/opt/<app>` separately from `docker-compose.yml`, the two can disagree, and the result is a syntactically present, semantically empty reference. Under a rule that says "a reference resolving to no local image contributes nothing", that application's images silently lose their protection while every guard reports satisfied.

So the rule is split by *well-formedness*, not by resolution. A well-formed reference that resolves to no local image names an image this host has not pulled and contributes nothing. A reference that is not well-formed — an empty repository or tag segment, a trailing `:`, a residual `${` — is an unresolvable reference set and abandons the run.

This is the same asymmetry the previous design argued for `grep -vxF -f` with an empty pattern file, arrived at from the other side. There, the degraded path had to be an explicit early return because the filter's natural behaviour was to match everything. Here the union's natural behaviour is to be *too small*, which is the same failure wearing different clothes.

### References are resolved to image IDs before comparison

`app-deploy` compares reference strings, normalised to a tagged form on both sides. That is correct for the narrow case it handles and does not survive widening.

A Compose file may pin by digest (`repo@sha256:…`), and such an image appears in `docker images` with its repository and **no tag**. A tag may move — the host's own `postgres:16` is a moving tag, and one of the ten dangling images is the digest it used to point at. One image may carry several tags. In every one of those cases the string that names an image is not the image.

So each reference in the keep set is resolved with `docker image inspect` to an image ID, and local images are compared by ID.

**The previous change's untagged-image exclusion is reversed here, and its reasoning is honoured rather than discarded.** That change excluded untagged in-namespace images because a *tag-shaped* reference set can never name a digest pin, so their absence from it was no evidence at all — and on that evidence, excluding them was the only safe move available. Under an ID-shaped keep set the evidence exists: a digest pin resolves and is protected on its merits, and an untagged image still absent from the union is genuinely referenced by nothing.

So the *rule* is reversed and the *principle* is kept: the absence of a tag is still not treated as evidence that nothing references an image. Entry 10 named these as its target; they are reached because a better keep set can see them, not because a guard was dropped.

### Removal is by tag where an image has tags, by ID where it has none — and each tag is re-checked

`docker image rm <id>` on an image carrying more than one tag fails with "image is referenced in multiple repositories (must be forced)". Since removal here is never forced, an image with tags is removed **through each of its tags**: each removal drops one reference, and the runtime deletes the image when the last one goes. An image with no tags at all has no reference to remove and is removed by ID.

That introduces a second resolution, and it is the one place this design can delete something a deploy is about to use. A tag is *selected* by the image ID it resolved to during enumeration and *removed* by name afterwards. Between the two, a pull can re-point that tag at a different image — a concurrent deploy, or any pull of a moving tag such as this host's own `postgres:16`. Removing it unchecked drops a reference to whichever image the tag names by then, and in the window between `docker compose pull` and `docker compose up -d --wait` that image has no container holding it, so the runtime's refusal never engages.

Each tag is therefore re-resolved immediately before its removal and skipped unless it still names the image it was selected as. This costs one `inspect` per candidate and closes the window without a lock and without `-f`.

`docker image prune` is not used, in either form. Its dangling filter selects by "has no tag", which would sweep in a digest-pinned image on the strength of a property this design has just finished establishing is not evidence. Untagged images are enumerated and filtered against the same keep set as everything else, so one rule governs the whole host rather than a targeted rule for tagged images and a blunt one for the rest.

Removal is never forced, for the reason the previous design gives and this one inherits: the runtime's refusal to remove an image a container holds is the only backstop standing between a defective keep set and a live image, and `-f` removes exactly that backstop. An individual refusal is a normal outcome and is tolerated and counted, not allowed to abandon the run — the enumeration steps are the ones whose failure is fatal.

### Unlike the deploy path, this run fails loudly

`app-deploy`'s reclamation ends in `|| true` because a maintenance step must never fail a deploy that already succeeded. Nothing depends on this one. A timer that abandons its run has no caller to damage, so it exits non-zero and leaves a failed unit that `systemctl list-units --failed` reports.

It also reports on every exit path, in the same split the previous change established and for the same reason — a run that silently matched nothing is indistinguishable from a run working correctly. A completed run reports how many images it considered and how many it removed, both deduplicated by image ID: `docker images` yields a row per tag, so a two-tag image would otherwise be counted twice on each side. The removed count is anchored to this run's own `docker image rm` invocations rather than read off the host's end state, because `app-deploy` is also removing images and a weekly window will occasionally overlap a deploy — a count that diffed the host would credit that deploy's work to this run, in the one report this change emits.

The reports go to the journal, and **nothing scrapes the journal**. That is a real gap and it is stated rather than papered over: the outer backstop remains `HostDiskPressure` at 90% full, which is very late. Closing it properly needs node-exporter's textfile collector and a staleness alert, which is a `platform/` change and is recorded in `docs/change-queue.md`. What this change buys in the meantime is that the failure is *recorded* on the host rather than swallowed.

### The duration bound is systemd's, not a `timeout` in the script

`app-deploy` wraps its reclamation in `timeout` and prints the bound's report from outside the bounded region, because a report emitted inside cannot survive the region being killed and the deploy session is the only place a report can go.

A systemd unit needs neither piece of that. `TimeoutStartSec=` bounds the run, and systemd itself records the timeout in the journal and marks the unit failed — from outside the process, which is where the previous design had to work to put its own timeout line. Reimplementing the wrapper inside the script would add a second bound that reports less well than the one already there. It follows that the duration-bound path is the one exit path the *run* does not report on, and the delta says so rather than obliging a line that cannot exist.

The wedged-runtime case this is for is unchanged: enumeration is as much a daemon call as removal, and the unit's bound covers the whole run.

### It is a new role, not more of `deploy_user`

`deploy_user`'s subject is the restricted deploy account: `/opt/<app>`, the `sudoers` rules, the forced commands, and the scripts those commands reach. This timer is host maintenance that reaches *across* every application, and belongs to none of them.

Putting it in `deploy_user` would also put it inside that role's Molecule scenario, whose `verify.yml` is already 700-odd lines covering the deploy account and per-deploy reclamation, and where a guard on this mechanism could not be exercised in isolation.

`image_prune` reads `deploy_apps` — the same inventory variable, not a copy — and asserts it by name before acting, per "A Role's Absent Required Input Is Reported by Name". It is within Ansible's scope under "Configuration Scope Stops at the Container Runtime": it templates no application service-definition file and starts, stops or restarts no application stack. It removes images, which is the runtime's own housekeeping. The converge arms the timer and never starts the service, so configuring the host is not also a prune of it.

### Local images are enumerated first, and that is what makes a lock unnecessary

The hazard worth checking is a deploy in flight while the timer runs. There are three orderings, not two, and the third is the one that bites.

A run that finishes entirely before the deploy delivers anything is uninteresting. A run that computes its keep set *after* the delivery reads the new Compose file, so the newly pulled image is in the keep set.

The third is a run that computes its keep set from the old Compose file and then enumerates local images after `docker compose pull` has landed the new one. That image is now on the host, is named by a Compose file the run never read, and — in the window between `pull` and `up -d --wait` — is held by no container, so the runtime's refusal does not engage. The per-tag re-check does not help: the tag legitimately still names the image the run selected. It would be removed, and the deploy would re-pull it or fail trying.

**So local images are enumerated before the keep set is computed, not after.** The interval between the two can then only ever *narrow* what a run removes: an image that appears during it was never a candidate, while a reference that appears during it is still honoured. Ordering the two the other way makes the same interval a window in which an image can be both a candidate and outside the keep set.

With that ordering and the per-tag re-check, no lock is needed. A `flock` shared with `app-deploy` would mean modifying a script this change otherwise does not touch, to take a lock it has no other use for, in order to protect windows that an ordering constraint and one `inspect` per candidate already close.

### Weekly, with a randomised delay and catch-up on boot

The high-rate source of superseded images is handled at the deploy. What remains arrives when a platform pin changes, when an application is retired, and when a moving tag moves — none of them daily events. A weekly run keeps at most a week of that, which against a ~1.4 GB static residue and a 75 GB disk at 15% is ample.

`Persistent=true` so a host that was down at the scheduled time runs on next boot rather than skipping a week silently, and `RandomizedDelaySec` so the run does not land on a fixed minute — the same reason unattended-upgrades randomises.

## Risks

**The union is computed too small and live images are removed.** The one failure that matters, and the one the first review of this design found two open paths into. Guarded, in order:

- an application's Compose file that cannot be rendered abandons the whole run;
- a rendered reference that is not well-formed abandons the whole run, which is what keeps an unset `.env` variable from silently dropping an application's protection;
- the render spans every declared profile, so a defined-but-never-started service is named;
- an enumeration naming no application abandons the run, rather than degrading to the container-state-only claim this design rejects;
- an enumeration the host does not carry at all abandons the run, reported distinguishably, rather than falling through to a container-only keep set — which is the same claim reached by a different route;
- an empty union removes nothing;
- every container's image is in the union independently of any Compose file, so the images actually in use are covered even if every Compose file were wrong;
- local images are enumerated before the keep set is computed, so an image that arrives mid-run is never a candidate;
- each tag is re-checked against the identity it was selected as immediately before it is dropped.

Behind all nine, the runtime refuses to remove an image a container holds, and removal is never forced. That refusal guards the *image* and not its individual tags, which is why a container's image is in the keep set in its own right rather than being left to the refusal alone: an image carrying two tags would otherwise lose one of them on every run.

The residual case is an image that is wanted, referenced by no enumerated application's Compose file under any profile, and held by no container. That image is indistinguishable from residue by any evidence on the host — it is what `traefik:v3.2` and `polinux/stress` look like — and removing it is the change's purpose. The cost is a pull.

**`deploy_apps` drifts from what is actually deployed.** An application deployed but not enumerated would have its images treated as residue. It cannot be deployed without being enumerated: the `sudoers` rule and the `authorized_keys` forced command are generated from this same list, so an application missing from it has no way to deploy at all. What *can* lag is the on-host copy, which is refreshed by a converge; the README states that consequence rather than leaving it to be discovered.

**A guard that cannot fail.** Every guard here is over a destructive operation, and the previous change recorded three assertions that produced green for reasons unrelated to what they claimed. Each guard is therefore mutation-tested — the thing it guards is removed and the assertion confirmed to go red — and `tasks.md` names that for each one individually rather than as a blanket instruction.

Two of the nine are exempt, and the exemption is stated here rather than left in the test plan, because it is a real limit on this argument. The **per-tag re-check** and the **enumerate-first ordering** are both observable only when the host's images change midway through a run, and a black-box Molecule scenario has no seam between the run's enumeration and its removal loop at which to change them. Neither is held by an assertion; both are held by review and by a static read of the installed script. They are also the two guards that close the concurrent-deploy window, which is to say the least-verified part of this design is the part that deals with the only actor that competes with it. `tasks.md` 2.11 records both with that reason, and 2.7 lists neither — an assertion that passes whether or not the guard exists is worse than an absent one, and that is exactly what a test written for either would be.

## Alternatives considered

**`docker image prune -af --filter until=168h`.** What entry 10 and the previous change's Alternatives section both name, and what this change was expected to be. Rejected on the `until` finding above: the window excludes nothing, so the mechanism is not "old and unused" but "not currently running", which loses a defined-but-never-started service's image and reaches a digest pin through a property that is not evidence. Put to the operator with the finding stated, 2026-09-07; the union reference set was chosen.

**`docker image prune -f` — dangling only, no `-a`.** Zero over-removal risk by construction, and it reclaims ~3.2 GB of the 3.221 GB. Rejected as insufficient: it reaches one of entry 10's three targets, leaves every superseded base image on the host permanently, and its safety comes from a filter this design has established is unsound for digest pins.

**Accepting a keep set that can be short, and leaning on container state.** The alternative to rendering across profiles and rejecting malformed references. Rejected because it converges on `prune -af` for everything not currently running, which is the outcome this design was chosen over — and it would do so silently, on the paths hardest to notice.

**A `flock` shared with `app-deploy`.** Rejected: it would modify a script this change does not otherwise touch, and the only window it closes is the one the per-tag re-check closes locally.

**Extending `app-deploy` to consider shared base images.** Rejected outright. It would give every application's deploy authority over `platform`'s images, which is the failure the previous design's namespace restriction exists to prevent, and it would re-solve the problem once per application instead of once per host.

**A cron entry rather than a systemd timer.** Rejected: the unit gets a duration bound, a recorded failure state, journal capture, and catch-up after downtime from the init system rather than from the script, and this repository already manages units through Ansible (`hardening`, `tailscale`).
