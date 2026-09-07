## Context

`app-deploy` is installed by the `deploy_user` role as a `root:root`, mode
`0755` script at `/usr/local/bin/app-deploy`, invoked as
`sudo /usr/local/bin/app-deploy <app>` by `deploy-receive`, which is itself the
forced command on every application's SSH key. Its whole body today is:

```bash
#!/bin/bash
set -euo pipefail
cd "/opt/$1"
docker compose pull
docker compose up -d --wait
```

Reclamation belongs inside this script. Everything below is about what it may
safely remove and when.

## Decisions

### The reclamation runs after `up -d --wait`, not before the pull

`docker compose up -d --wait` returns only once every healthchecked service is
healthy. Running reclamation after it means the images the new containers hold
are held by *running containers* at the moment removal is attempted, and
`docker image rm` refuses to remove an image a container uses. That refusal is
the real safety property here: even a defective filter cannot remove the image
production is running on, because Docker will not let it.

Running it before the pull would have the opposite property — the live image
would be unprotected precisely while nothing was running it.

### Scope is the application's own namespace, not everything its Compose file names

The obvious implementation — take `docker compose config --images`, remove
every local image not in that set — is wrong, and dangerously so. That set
includes `postgres:16-alpine`, `traefik:v3.7.10`, `alpine:3.19`: base images
that other applications on this host also use. Removing "every `postgres` tag
that *this* application does not reference" would make `platform`'s
`postgres:16` a candidate, with nothing standing between it and deletion except
the accident of a container currently running.

Reclamation is therefore restricted to references matching
`ghcr.io/<owner>/<app>:<tag>` — the namespace an application publishes its own
builds into. Within it, every tag the application's Compose file does not
currently reference is removed.

The consequence is worth stating plainly: an application that runs a *shared*
image accumulates nothing here, and cleaning that up is not this mechanism's
job.

Two edges of that namespace need naming, because both are silent when wrong.

An image referenced by *digest* rather than by tag sits inside the namespace —
it carries the repository name — but appears in `docker images` with no tag,
and can never appear in a tag-shaped reference set. Treating it as unreferenced
would delete an image the application may be pinned to. Untagged members are
therefore left alone; the periodic prune this change defers to is the mechanism
that eventually reaches them.

And the whole scheme rests on the application's deploy name being the second
segment of its image repository — true of `commerce-ops`, unstated until now,
and unenforced. Where it does not hold the namespace is empty and reclamation
does nothing at all, indistinguishable from working. `platform`, the other
enumerated application, is already in this position for a different reason: it
publishes no image of its own and so has nothing to reclaim by design.

### The owner segment is a wildcard, deliberately

The pattern matches any owner, not the current one. This is not laxity — it is
the case that actually occurs.

An owner-pinned pattern strands, permanently, every image published under any
owner the application has since left: no future deploy would ever name that
owner again, so nothing would ever revisit them. Each transfer would leak its
whole pre-transfer tail, and the leak would be invisible.

The case that exposed this is the reason the pattern was examined at all.
`commerce-ops` moved from `ghcr.io/shatynska/commerce-ops` to
`ghcr.io/fuperia-it/commerce-ops` on 2026-09-07, and of the 190 stale images on
the host, **all 190 are under the previous owner** against exactly one under the
current. That particular backlog is cleared by hand rather than by this pattern
(see below), so it is no longer what the wildcard is *for* — but transfers will
happen again, and the wildcard is what keeps the next one from silently
stranding its tail.

What the wildcard costs: an unrelated `ghcr.io/<someone-else>/<same-app-name>`
image on the same host would be a candidate. That is a namespace collision on
the application's own short name, on a single-tenant host whose deployable
applications are enumerated in version control. Against a failure mode that has
already occurred once, it is the right trade.

### An unavailable or empty reference set reclaims nothing

The reference set is computed first, and a run that cannot compute it — or
computes it empty — removes nothing.

This is not defensive padding. The natural shell realisation of "remove what is
not referenced" is `grep -vxF -f <(docker compose config --images)`, and `grep`
with an empty pattern file matches no line, so `-v` inverts it to match *every*
line.

A `config --images` that fails — an older Compose plugin, an interpolation
error, a Compose file that `up` tolerates and `config` does not — therefore does
not degrade to "reclaim nothing". It degrades to "reclaim the entire namespace",
and the `|| true` below guarantees nobody is told.

Two details of that comparison are load-bearing in their own right. The `-x` is
not decoration: `-F` alone matches substrings, so a reference-set entry that is
a prefix of another local tag would protect the wrong image, and whole-line
matching is what makes "referenced" mean the same thing on both sides. And both
sides must agree about tags — `docker images --format '{{.Repository}}:{{.Tag}}'`
always emits one, while a Compose file naming an image without a tag may or may
not be rendered with an explicit `:latest` depending on plugin version. A
mismatch there makes the *live* image a candidate on every deploy: harmless,
because a running container holds it, but it prints a refused removal every
time, which is the recurring noise this document elsewhere says invites someone
to add `-f`. References are therefore normalised to a tagged form before
comparison.

Running containers would still be protected by the runtime's refusal. What
would not be protected is a service defined but scaled to zero — which is the
exact case the reference set is taken from Compose rather than from running
containers in order to protect. The degraded path would silently abandon the
property the non-degraded path was designed for.

### Removal is never forced

The runtime's refusal to remove an in-use image is the backstop this design
rests on, so the implementation is constrained not to override it: plain
`docker image rm`, never `-f`, and never `docker image prune -a`.

One qualifier, because the backstop is narrower than it first reads: Docker
refuses removal where it would drop an image's **last** reference. An image
carrying a second tag is untagged instead, and the command succeeds. That is
harmless here — the image survives, and a running container still holds it — but
it means the refusal is a guard on *images*, not on tags, and a fixture built
without noticing will pass for the wrong reason (see tasks.md 2.4).

Stated as a fact about Docker rather than as a rule about this script, that
backstop would not survive contact with maintenance. Refused removals are the
*normal* outcome here — the live tag is refused on every single run — so the
step routinely prints conflicts while appearing to do nothing wrong, which is
precisely the shape that invites someone to add `-f` and make the noise stop.
The requirement therefore says removal SHALL NOT be forced, and tasks.md 2.4
asserts it.

What holds that assertion is worth naming precisely, because it is not CI:
`iac-cicd-pipeline` puts the Molecule suite in the **advisory** tier, explicitly
not a required status check, and its own scenario says a failing scenario leaves
the required checks unaffected. So a future pull request adding `-f` would merge
with a red advisory check unless someone read it. What actually catches it is the
`molecule test` run in `build:verify` and review — with the CI result as a signal
to read, not a gate that stops.

### Retention is "what Compose currently references", not "the last N tags"

Keeping the previous tag or two would make rollback a local operation rather
than a pull. It is not worth it: GHCR retains every tag, the packages involved
are public (see Risks), and a rollback that re-pulls is seconds slower and no
less certain. "Keep last N" also needs a stable ordering
over tags that are content hashes, which is a sorting problem with no correct
answer — creation time is the only usable key and it is not what "last N
deploys" means.

Taking the reference set from `docker compose config --images` rather than from
the running containers keeps a service that is defined but temporarily scaled
to zero from having its image reclaimed out from under it.

### A failed reclamation never fails a deploy that succeeded

The script runs under `set -euo pipefail`, and by the time reclamation starts
the deploy has already succeeded — the containers are up and healthy. A
non-zero exit from a cleanup step would turn a healthy deploy into a failed
one, fail the SSH session, and fail the calling workflow, for a disk-hygiene
step that has no bearing on whether the application is serving.

Reclamation therefore ends in `|| true`, and its individual removals are
tolerated failing.

That swallows the only per-run signal, so two things replace it. The step
prints one line — how many candidates it found and how many it removed — into
the deploy session, which `deploy-receive` already carries back to the calling
workflow, so a run that matched nothing is visible to anyone reading a deploy
log rather than only to whoever eventually looks at the disk.

Something is printed on *every* exit path, though not the same thing: a
completed run prints its counts, while a run abandoned early — empty or
undeterminable reference set, or the duration bound — prints which of those
ended it. The paths worth reporting on are
exactly the ones that end early, so a report reachable only on the ordinary path
would report only when nothing is wrong. And the outer
backstop is named rather than merely assumed: `HostDiskPressure`
(`platform/docker-compose.yml`, the `HostDiskPressure` rule), which alerts on
`node_filesystem_avail_bytes{mountpoint="/"}` against a threshold, is what
catches a reclamation that has silently done nothing for weeks.

This is the same reasoning `amazon_reports_upload`'s `ops_heartbeat.py` states
for its own failures: a maintenance concern must never take down the thing it
maintains.

### The one-time backlog is cleared by hand, not by the first deploy

Reclamation is bounded in *outcome* — it exits zero whatever happens — but not
in *duration*. Nothing in `|| true` bounds elapsed time, host I/O, or a
container daemon that stops answering partway through.

For the steady state that does not matter: one superseded tag per deploy, a few
hundred megabytes, unlinked in about as long as the pull that preceded it. For
the *first* run after this merges it matters a great deal. That run faces the
accumulated backlog this change was written for — ~190 images and ~42.88 GB, by
the proposal's own measurement — and it would execute inside a production
deploy, on a `cx33` whose single root filesystem also carries `platform`'s
Postgres, Prometheus, Grafana and Traefik, while the deploying SSH session and
the CI job that opened it stay open and silent.

Running it there buys nothing the mechanism needs to prove. The backlog is
therefore cleared once, by the operator, on the host, as a rollout step — and
the first deploy after that faces the ordinary single-tag case like every
deploy after it.

**The manual step is held to the same constraints as the automated one.** This
matters more than it might seem: the hand path removes ~190 images where the
automated path removes one, so it is the *riskier* of the two, and specifying it
loosely would put the change's largest single mutation outside every guard the
rest of this document argues for. The obvious command for "clear the backlog" is
`docker image prune -a`, which is exactly the semantics rejected under
Alternatives — it removes any image no container currently runs, which during a
restart or an incident is a far broader claim than intended. It is not what runs
here. The step is:

```bash
sudo bash -s <<'SH'
set -euo pipefail
cd /opt/commerce-ops
keep=$(docker compose config --images | sort -u) || keep=""
[ -n "$keep" ] || { echo "reference set empty or unavailable; aborting" >&2; exit 1; }
docker images --format '{{.Repository}}:{{.Tag}}' \
  | grep -E '^ghcr\.io/[^/]+/commerce-ops:' \
  | grep -v ':<none>$' \
  | grep -vxF -f <(printf '%s\n' "$keep") \
  | xargs -r -n1 docker image rm || true
echo "remaining:"; docker images --format '{{.Repository}}:{{.Tag}}' | grep -cE '^ghcr\.io/[^/]+/commerce-ops:' || true
SH
```

The two tolerances are not sloppiness. `keep=$(…) || keep=""` exists so a failing
`docker compose config` reaches the guard's own message instead of being killed
by `set -e` one line earlier — the abort should say why it aborted. And
`xargs … || true` exists because `xargs` exits 123 if *any* single removal is
refused, while this document establishes that refused removals are the **normal**
outcome: without it the clearance can do exactly the right thing and still
report failure, at precisely the moment the reasoning above says an operator who
sees the specified command fail is one step from the unguarded form.

It runs privileged, and not from an enumerated operator account. Those accounts
carry `docker` group membership but no `sudo` at all, and `/opt/commerce-ops` is
`drwxr-x--- deploy:deploy` — checked on the host on 2026-09-07: `cd` is refused,
so `docker compose config --images` cannot run and the guard aborts. That is the
safe failure, but an operator who cannot make the specified command work is one
step from `docker images | grep commerce-ops | xargs docker image rm`, which is
the unguarded form this whole section exists to prevent. The clearance runs over
the same privileged path `ansible-playbook` uses to reach the host, in the same
session as the rollout.

The `bash -s` wrapper is deliberate too: the guard's `exit 1` must end the
clearance, not the operator's login shell.

Namespace-scoped, untagged members excluded, empty reference set aborts, plain
`docker image rm` with no `-f`, no `prune`. The same five constraints, in the
same order, as the script — which is the point: the hand path is the automated
path with the loop unrolled, not a different and blunter operation that happens
to free the same disk.

**On doing this from an operator's machine at all.** This is not the deploy
pipeline, and no application, image or configuration reaches production by this
route — it removes images nothing references. The project rule that local
production credentials are "for reading … and not for applying" is written about
`terraform apply`, and this repository has no Ansible pipeline: running
`ansible-playbook` against the host from an operator's machine is already how
every host-configuration change reaches production here, including the one that
installs this very script. The clearance sits on exactly that footing, in the
same session, and nowhere further.

It costs the change its most dramatic confirmation — "42.88 GB disappeared" —
and replaces it with a better one. Observing that the single tag a deploy
superseded is gone proves the behaviour that will run on every future deploy,
where the bulk figure would only ever have proved a one-off.

Separately, and for the steady state rather than the backlog, the whole
reclamation step is wrapped in a `timeout` — enumeration as well as removal.
Bounding only the removals would leave the case this is for wide open:
`docker images` and `docker compose config` are calls to the same daemon the
removals are, so a daemon that stops answering hangs the step before a
removal-only bound could ever engage. Expiry is a reclamation failure like any
other: swallowed, deploy still successful.

The `timeout` wraps the work, and the *timeout line* does not sit inside it. A
report emitted from within the bounded region cannot survive that region being
killed, which would make "a run abandoned at its duration bound SHALL say so"
dead text — the one run most worth hearing about would be the silent one. The
wrapper prints that line from `timeout`'s exit status instead.

Only that line moves outside, and only a reason travels with it. The exit status
carries no counts, and no count survives the kill anyway, so a completed run
still prints its own `considered N, removed M` from inside the region. Pushing
the whole report outward would have bought the timeout path a line at the cost
of the counts on every ordinary path — trading the signal that gets read for the
one that almost never does.

## Risks

**A removal the filter should not have made.** Bounded by Docker's own refusal
to remove an in-use image, which is enforced regardless of what the filter
computes, and by the preceding two decisions for the degraded and forced cases.
The worst outcome is an image removed that nothing currently holds, recovered
by a pull.

That recovery is the compensating control for every over-removal risk here, and
it is worth establishing rather than assuming — most of all for the
previous-owner namespace, which is where the hand clearance removes 190 images
at once (the first *deploy* faces the ordinary single-tag case; see below). Checked on 2026-09-07: `ghcr.io/shatynska/commerce-ops` is a
*public* package, and three tags taken from the host's own image list
(`a5fd2dba…`, `d18a89d0…`, `2c6bbda5…`) each return HTTP 200 for their manifest
against an anonymous GHCR pull token. Pre-transfer builds therefore remain
pullable, and remain pullable even on the path `iac-host-configuration`'s
"Host Authenticates to GHCR for Application Image Pulls" explicitly permits —
no credential configured at all — because no credential is needed to read a
public package.

**Reclamation silently doing nothing.** The `|| true` that stops it failing a
deploy also stops it reporting. This is why the Molecule scenario must assert
that a superseded image is actually *gone* after a second deploy, rather than
that the script ran — a test asserting the latter would pass against a
reclamation step that matched nothing at all.

## Alternatives considered

**A weekly `docker image prune -af --filter until=168h` and nothing else.**
Simpler, and it also handles dangling images and retired applications, which
this change does not. Rejected as the *primary* mechanism because its steady
state is a week of accumulated images rather than one, and because it is
untargeted: it removes any image no container currently runs, which on a host
where an application is briefly stopped is a broader claim than intended. It
remains the right complement, and is queued as its own change.

**Reclamation in each application's deploy workflow.** Rejected: it makes every
application repository responsible for the host's disk, has to be re-solved on
each onboarding, and would run with whatever GHCR-scoped permissions the
workflow has rather than as the host's own maintenance. `app-deploy` is already
the one place every application's deploy converges.

**`docker compose down --rmi` on the previous state.** Rejected: it operates on
Compose's notion of the project rather than on images, removes images belonging
to services regardless of namespace (the shared-base problem above), and would
have to run before the new state is up, which is exactly when the live image is
unprotected.
