## Context

See `proposal.md` — Why. Two constraints shape everything below.

**The `""` contract.** `platform_data_volume_device` defaults to `""` rather than
being undefined, and `defaults/main.yml:1-9` explains that the empty string *is*
the signal meaning "discover it on-host". Any fix that reaches for
`| mandatory`, for an undefined default, or for a literal device path breaks a
contract that is written down and correct. This is also why the general
required-input requirement in the delta spec is careful to say the role decides
what "not supplied" means: for `platform_data_volume_device` empty is supplied,
and for `hardening_ssh_allowed_cidrs` an empty list is a deliberate
tailnet-only-SSH posture, not an omission.

**The Compose side is not free.** `platform/docker-compose.yml` is on
`platform-deploy.yml`'s `paths:` filter, so merging touches production through a
gated deploy that recreates the services whose definitions changed. The Ansible
side merges without deploying anything and takes effect at the next
operator-initiated `host-baseline.yml`. Those are two different delivery
mechanisms in one change, which is a sequencing question rather than a reason to
split — see Decision 6.

Production state as read on 2026-09-07 from `platform-postgres-1`:
PostgreSQL **16.15** (`postgres:16` currently resolves there), all eight platform
services defined in the stack are up and healthy, seven of them already on exact
release tags.

## Goals / Non-Goals

**Goals:**

- An operator running `host-baseline.yml` against a host with no attached volume
  reads the question they need to answer, not a Jinja traceback.
- Every role that consumes a caller-supplied input with no safe default on every
  run says so before it acts, and they all say it the same way.
- No shared-stack service resolves its version at deploy time — enforced as far as
  a static read can enforce it, and stated honestly where it cannot.
- Every failure path this change creates is covered by an automated scenario,
  because those are precisely the paths nobody exercises by hand.

**Non-Goals:**

- Changing *where* the device path comes from. On-host discovery stays.
- Introducing any default that would let a run proceed with a guessed firewall
  CIDR, a guessed deploy key, or a guessed block device.
- Asserting `tailscale_auth_key`. It is conditionally consumed, and demanding it
  unconditionally would break a re-converge of an already-joined host — Decision 3a.
- Upgrading PostgreSQL. The pin names the version already running.
- Widening Grafana's exposure. The root URL is corrected to the tailnet address
  Grafana is already bound to; it does not become a reason to publish it further.
- A general audit of image pins elsewhere in the repository. `postgres:16` is the
  only floating one; the delta spec states the rule so the next one is caught.
- A check that decides, on its own, whether a tag floats. That is a property of
  the publisher and not readable from a committed file — Decision 7.

## Decisions

### 1. Guard the discovery result in the consuming task's condition, rather than reordering the block

The `set_fact` at `tasks/main.yml:25-28` is guarded only by
`platform_data_volume_device | length == 0`. Extend that guard so it also
requires the discovery to have found something:

```yaml
when:
  - platform_data_volume_device | length == 0
  - platform_data_volume_by_id.files | default([]) | length > 0
```

The empty case then falls through to the `assert` that already exists, unchanged,
and the operator gets the diagnostic that was written for them.

`| default([])` is load-bearing, not defensive noise, and for a stronger reason
than the skipped-task one. `platform_data_volume_by_id` can be **wholly
undefined**, not merely missing its `files` key: a run that excludes the `find`
task by `--tags` or `--skip-tags` never registers the variable at all, and neither
does a second invocation of the role in a play where the first supplied a device.
The filter has to survive an undefined register, which it does — Ansible's
undefined type chains through attribute access, so `default([])` catches
`platform_data_volume_by_id.files` whether the register is absent, present without
`files`, or present with it.

The secondary case is the ordinary one: when the caller supplies a device the
`find` task is skipped and the register holds `{'skipped': True, 'changed': False}`
with no `files` key.

*Alternatives considered.* Moving the `assert` above the `set_fact` and asserting
on `files` instead — rejected because the assert would then have to be duplicated
or reworded to cover both the supplied and the discovered case, and its current
single statement covers both. Wrapping the block in `block`/`rescue` — rejected
as far more machinery than a `when:` clause for a condition that is not an
exception.

### 2. Sort the discovery result rather than failing when it is ambiguous

`files[0]` becomes `files | map(attribute='path') | sort | first`. With one
attached volume — the case in production today — this is byte-for-byte the same
device. With two, the pick is stable across runs instead of depending on
directory-read order.

*Alternative considered and rejected: fail when more than one device matches.*
It is defensible — an ambiguous pick is arguably worse than a refusal — but this
role does not own what else may be attached to the host, and a second Hetzner
Volume mounted for a reason unrelated to `platform/` would then break the
baseline playbook for every host. Determinism is what the audit identified;
turning ambiguity into a hard failure is a policy decision that deserves its own
proposal rather than being folded in. Recorded in `docs/change-queue.md`.

The sort is verified, not merely implemented. Nothing in the suite exercises the
multi-device path today, so a later edit back to `files[0]` would pass every
scenario — the same failure mode Decision 4 argues against for the empty case. The
fixture is cheap: a privileged container can create two symlinks under
`/dev/disk/by-id/` named so that the lexicographic winner is *not* the one a
directory read would return first, which is what makes the assertion discriminate
rather than pass by luck.

### 3. `hardening` and `deploy_user` assert definedness, not non-emptiness

The assertion goes first in each role's `tasks/main.yml` — before
`Ensure UFW is installed` and before `Create the deploy group` respectively — so a
missing input is a refusal to proceed rather than a half-configured host, which is
the delta spec's *check precedes the tasks* scenario.

Each asserts `<var> is defined` and that it is a sequence. Neither asserts
`| length > 0`. For `hardening_ssh_allowed_cidrs` an empty list is a coherent,
deliberate posture: the role separately allows SSH from the tailnet CGNAT range
(`tasks/main.yml:55-60`), so an empty public-SSH CIDR list means "tailnet-only
SSH", which is stricter than what prod runs and is not an error. For `deploy_apps`
an empty list means "no application may deploy to this host", which is likewise
restrictive rather than wrong. Asserting non-emptiness would forbid configurations
safer than the ones we ship.

`hardening_web_allowed_cidrs` is untouched: it has a documented safe default of
`[]` (closed), so it is not a member of the class this requirement covers.

### 3a. `tailscale_auth_key` is deliberately not asserted

`tailscale/defaults/main.yml:2-5` documents it in exactly the same words as the
other two, which is what makes leaving it out look like an oversight. It is not.
`tasks/main.yml:84` consumes it inside a task guarded by a `when:` that skips when
the host is already on the tailnet, so on a re-converge of the prod host — the
common case — the variable is never evaluated and need not be supplied. An
unconditional assert would start demanding it on every run and break a working
path. That is why the delta spec's requirement is scoped to inputs consumed on
every run, and why it carries a scenario saying a conditionally-consumed input
must *not* be demanded when its step is skipped.

Reporting that case well is worth doing, and is harder than it looks: the
diagnostic would have to fire under the same condition as the join, which means
naming that condition once instead of restating a four-limb expression whose
`POLARITY` comment warns that reading it the wrong way silently stops a host
joining the tailnet. The role also has no Molecule scenario at all, so there is
nothing to catch a regression in the one mechanism this project's deploy path
depends on for reachability. Queued (task 7.2), not folded in.

### 3b. A Molecule scenario for `hardening`, but not for `deploy_user`

`hardening` gets a failure-path scenario, using the same shape as
`platform_data_volume`'s. Note carefully what that does and does not establish:
`platform_data_volume`'s scenario does **not** also demonstrate this requirement.
Its `""` is a supplied value the role gives a meaning to, which the requirement's
own empty-value clause explicitly excludes — that scenario demonstrates the
*volume* requirement instead. So the general required-input requirement rests on
`hardening`'s scenario alone, and claiming two independent demonstrations would
overstate the coverage.

`deploy_user` does not get a scenario of its own, and that argument has to carry
more weight given the paragraph above. Its assertion is the same construct as
`hardening`'s, over the same class of value, failing at the same point in the play
— so a scenario would re-run a mechanism rather than reach a distinct behaviour,
and task 4.2's regression check across the three existing scenarios establishes
that the new assertion does not break the supplied case. That is the whole of the
argument. It is deliberately *not* a cost argument: a
failure-path scenario aborts on the role's first task, so its marginal cost is one
container create/destroy cycle — `platform_data_volume`'s entire scenario runs in
1m35s — and pleading CI time for something that cheap would be a bad reason
dressed as a good one. If the assertion pattern later diverges between roles, that
is when a scenario per role starts earning its place.

### 4. The new Molecule scenario asserts the failure, using this repository's existing pattern

`molecule/default/` supplies `platform_data_volume_device` explicitly and so has
never executed the discovery block at all. A container also has no
`/dev/disk/by-id/scsi-0HC_Volume_*` entry, which makes the empty-discovery case
the *natural* case in a container rather than one needing a fixture — the new
scenario supplies no device and lets discovery find nothing.

The scenario follows `deploy_user/molecule/ghcr-credential-rejected/` in its
*failure-capture* shape: `block`/`rescue` in `converge.yml` writing the outcome to
a JSON marker file on the instance, and `verify.yml` asserting on that file. Its
`molecule.yml` comes from `platform_data_volume`'s own `default` scenario instead,
since the platform stanza is role-specific — with one mandatory change: **a
distinct instance name.** Every scenario in this repository names its instance
uniquely, and two scenarios of the same role sharing a name collide on `create`
whenever a container from the sibling is still up. That indirection is
required, not stylistic — Molecule runs converge and verify as two separate
`ansible-playbook` invocations, so no fact survives between them. Recording the
success branch as well as the failure branch matters for the same reason it does
there: if the guard is later widened so the role stops failing, converge succeeds,
records `succeeded`, and verify fails on it. A scenario that recorded only the
failure branch would go green in exactly the case it exists to catch.

`verify.yml` asserts that the recorded failure came from the `assert` task and
that its message names the volume — not merely that the run failed. A run that
failed on the index error would also be "a failure", and it is the one being
fixed.

New scenarios need no workflow edit: `ansible-verify.yml` discovers roles
carrying a `molecule/` directory and runs `molecule test --all`.

### 5. Pin PostgreSQL to `16.15`, the version production is running

Read from the running container rather than chosen from the registry, so the
deploy stays on the PostgreSQL version already in service. Picking "the latest
16.x" instead would fold an unreviewed minor upgrade of the shared database into a
change about consistency, and the deploy's approver would be approving a diff
whose real consequence is invisible in it.

**This is not the same as a no-op.** Docker Hub rebuilds official-image tags in
place for base-OS patches, and `app-deploy` runs `docker compose pull`
(`deploy_user/tasks/main.yml:61-66`), so `postgres:16.15` may resolve to a
different digest than the one running — the same PostgreSQL version on a rebuilt
Debian layer set. The consequence is still a restart with WAL replay rather than a
data migration, and `pg_isready` plus the stated revert path cover it, but the
approver should be told the accurate thing.

*Alternative considered: pin by digest,* as `iac-cicd-pipeline` requires of
Molecule's images. Rejected here as a mismatch of purpose, and the paragraph above
does not overturn it: a Molecule image determines what the suite tested and must
be reproducible across machines and time, so a rebuild under a fixed tag is
exactly the hazard there. A stack image is deployed to one host from a diff a
human approves, a base-OS patch under an unchanged database version is usually
what you want, and an exact version tag is legible in review where
`sha256:f1c3376…` is not. The delta spec therefore admits either form.

### 6. Both Compose edits ship in one pull request, not one each

Two edits, one gated deploy, one approval, one recreate of `platform-postgres-1`
and `platform-grafana-1`. Splitting them into separate pull requests buys a
finer-grained rollback of two independent one-line changes at the cost of a
second production deploy and a second approval, and Grafana would be recreated
twice. It also does not reduce the blast radius of either edit, since a deploy
recreates only what changed.

### 7. Both static checks go in `.github/tests/`, not into a new mechanism

AGENTS.md scopes that suite to "any committed file the pipeline reads or
executes … so long as the assertion is a static read of a committed file".
`platform/docker-compose.yml` is read and deployed by `platform-deploy.yml`, and
both new assertions are pure static reads of it:

- **no shared-stack service names a tag less specific than a release** — the
  *necessary condition* half of the pinning requirement, and deliberately not the
  whole of it. Which tags float is a property of the publisher: PostgreSQL
  releases `MAJOR.MINOR`, so `postgres:16` floats and `postgres:16.15` is a
  release, while the other seven images release `MAJOR.MINOR.PATCH`, where a
  two-component tag would float.

  The check is therefore a **floor on specificity, never a ceiling**: reject
  `latest`, other channel tags, and a bare series like `16` or `v3`; accept
  anything naming two or more version components. A ceiling — the round-1 draft's
  "reject major-minor tags" — rejects this change's own `postgres:16.15`, which is
  how the contradiction arose. The floor catches the actual defect and rejects
  nothing currently correct. Its residue is hypothetical rather than live: **no image in
  the file after this change falls in that class** — all eight name an exact
  release under their own publisher's scheme. A tag *such as* `traefik:v3.7` would
  pass the floor without being a release, and that is the shape the test's
  docstring should describe. It is carried by the human review every stack edit
  already passes through, rather than papered over. The suite already has `parse_image_reference` and `CONTENT_DIGEST`,
  written for the Molecule pinning requirement, so this reuses them.
- **the dashboard's base URL is not a literal address** — the *configured base
  URL* scenario. This is the half of the Grafana fix that can be checked without a
  running host; the deploy-time confirmation in the Migration Plan covers the
  other half. Without it the only thing standing between `localhost` and the file
  is that someone remembers, which is how it got there.

PyYAML is pinned in `.github/requirements-ci.txt`, so neither check adds a
dependency or a new tier. `terraform test` cannot express either, which is exactly
the gap that suite exists to fill.

### 8. Resolve the header caveat by observation; do not restate it

`platform/docker-compose.yml:6-10` warns that the monitoring tags were pinned
without network access to confirm they resolve. Every one of them is running in
production and healthy (all eight services the stack defines), which is a stronger confirmation than a registry query
would have been. The caveat is deleted rather than reworded — a warning that has
been answered and left in place trains readers to skip warnings.

The commit-message paragraph at lines 1-5 goes with it: it records what a past
change did, which version-control history already owns. This is a single instance
of the class `docs/change-queue.md` entry 3 covers; that entry stays, because it
is about the repository-wide policy and this is one file already being edited.

## Risks / Trade-offs

**The gated deploy recreates the shared database container.** → The PostgreSQL
version is unchanged, so this is a restart, not an upgrade: PostgreSQL replays WAL
and comes back. It is not guaranteed to be the identical image — see Decision 5 on
in-place tag rebuilds — but a rebuilt base layer under the same server version does
not change on-disk format. Data is on the named `postgres_data` volume, untouched
by a recreate. `platform-postgres-1` declares a `pg_isready` healthcheck, so a
failure to come back is visible in the deploy rather than discovered later. The
dependent applications reconnect; a brief connection error during the restart is
expected and is the same window every previous platform deploy has had.

**`| default([])` could mask a real fault in `find`.** → It cannot: `find`
failing is a task failure that aborts the play before the `set_fact` is reached.
`default([])` only ever covers the deliberately-skipped case.

**The new scenario passes for the wrong reason.** → A container legitimately has
no matching device, so a scenario that merely asserted "the run failed" would
pass even against the unfixed role, which fails there too — on the index error.
This is why `verify.yml` asserts on the failing task's identity and message, not
on the fact of failure. The test author should take a baseline against the
unfixed role and confirm it fails on `list object has no element 0`, then again
after the fix.

**Grafana's root URL depends on `.env`.** → `GF_SERVER_ROOT_URL` becomes
`http://${GRAFANA_BIND_ADDRESS}:3000`, and if `GRAFANA_BIND_ADDRESS` were ever
empty, Compose interpolates it to nothing and the root URL becomes `http://:3000`
— broken, but visibly so. `platform-deploy.yml:100-120` already fails the deploy
on an empty or non-IPv4 value before writing `.env`, and the same variable
already gates the port publication on line 271, so an empty value never reaches a
running stack.

**Two delivery mechanisms in one change complicate `ship:confirm`.** → See
Migration Plan; the two halves are confirmed separately and the change is not
complete until both are.

**The fix makes legible a limitation it does not remove.** → After this change a
host with `volume_enabled = false` fails `host-baseline.yml` with a clear message
instead of an obscure one; it still fails. That is correct — the volume is a
stated dependency of the `platform/` services that bind-mount it, and the delta
spec now says so explicitly. But `iac-data-volumes`' *Volume toggle disabled
creates nothing* scenario describes a supported Terraform configuration, and no
artifact previously recorded that Ansible cannot converge a host in it. It is
recorded here so the next reader meets the two facts together rather than
discovering the second by running into it.

## Migration Plan

1. Merge the work pull request. `platform-deploy.yml` fires on the `platform/**`
   path and waits for a `production` Environment approval, with the exact diff in
   the job summary.
2. Approve. Confirm the deploy is healthy: `platform-postgres-1` reports
   `postgres:16.15` and `(healthy)`, `platform-grafana-1` is `(healthy)`.
3. **Confirm the Compose half by observation.** Read the base URL Grafana actually
   serves, from a tailnet peer, with no credential:

   ```sh
   curl -s http://<GRAFANA_BIND_ADDRESS>:3000/login | grep -o 'appUrl":"[^"]*'
   ```

   `/login` is unauthenticated and embeds Grafana's boot data, `appUrl` included.
   **Before** (captured on the live host, 2026-09-07):
   `appUrl":"http://localhost:3000/"`. **After**: it must read the tailnet address
   the stack is published on. This is a server-side read of the value Grafana
   builds every link and redirect from, not a restatement of the Compose file.

   Two observations that look natural here do **not** work, and were tried:
   `/api/frontend/settings` returns 401 on Grafana 12.3 without a credential, and
   there is no "View in Grafana" link to follow — alerting is Prometheus plus
   Alertmanager, and this stack's Slack receiver
   (its `alertmanager_config` Slack receiver) emits only `summary` and
   `description`, no URL of any kind. A panel's share link is built client-side from the
   browser's own location and never reads `root_url`.
4. **Confirm the Ansible half by observation.** Run `host-baseline.yml`. It is
   idempotent and this change adds no task that acts on the host, so the expected
   result is an unchanged converge against a host whose volume *is* attached —
   which confirms the guard did not break the working path. The failure path
   itself is confirmed by the Molecule scenario rather than by detaching the
   production volume, which is not an experiment worth running.
5. Open the archive pull request once both are confirmed.

**Rollback.** Revert the pull request; the revert's merge re-triggers
`platform-deploy.yml` and redeploys the previous definitions through the same
gate. The Ansible half needs no rollback deploy — it takes effect only at the
next `host-baseline.yml` run.

## Open Questions

None. Step 4's proposal — that the Ansible half's observable effect is an
unchanged converge, with the failure path evidenced by Molecule rather than in
production — is the operator's to accept or to replace with something they would
rather see; it is not a deferred decision, and nothing in the specs, the approach
or the tasks turns on the answer.
