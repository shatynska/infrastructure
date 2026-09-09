## Context

Three periodic jobs run in this system: `drift.yml` nightly, `pre-commit-autoupdate.yml`
weekly, and the `prune-host-images.timer` unit weekly on the host. Nothing watches any
of them.

The evidence that this matters is not hypothetical. `pre-commit-autoupdate.yml` failed on
2026-08-24, 2026-08-31 and 2026-09-07 with the same error. Each run was red in the Actions
tab, and GitHub emailed the workflow file's last committer each time. The defect survived
three weeks and was found by a person reading the Actions tab for an unrelated reason.
`open-autoupdate-pr-with-app-token` repaired the cause and explicitly did not repair the
silence.

Two facts about the current state shape everything below.

**The channel is what failed, not the mechanism.** Three notifications were delivered and
three were not read. A design that terminates in "GitHub notifies someone" re-picks a
channel with a measured read rate of zero in this repository.

**A failure alarm cannot cover a job that stops running.** GitHub disables
schedule-triggered workflows after 60 days of repository inactivity — README already
carries the manual re-enable procedure — and a systemd timer that stops firing leaves no
failed unit. In both cases there is no failure event to react to. This is the same
distinction `docs/change-queue.md` entry 15 reached from the host side: "an alert on
staleness rather than on failure — a unit that stops being scheduled at all produces no
failure to alert on."

This change delivers queue entries 32 and 15 together, at the operator's direction, because
they are one problem — *a periodic job stopped producing evidence* — observed at two
locations.

## Goals / Non-Goals

**Goals:**

- A red run, a run killed mid-flight, and a run that never happened all raise the same
  alarm.
- The alarm arrives somewhere that is actually read.
- A scheduled workflow added later cannot be merged unmonitored, without anyone
  remembering this change exists.
- One mechanism covers continuous integration and the host, rather than two.

**Non-Goals:**

- Making the third-party observer's own configuration verifiable from the tree. It is not,
  and this design says so rather than implying otherwise — the same limit
  `open-autoupdate-pr-with-app-token` accepted for its App secrets.
- Alerting on what a periodic job *found*. `drift.yml`'s drift issue is a separate,
  working mechanism and is untouched; this change is about whether the run happened and
  whether it succeeded.
- Any change to the platform stack's own Watchdog heartbeat, its Alertmanager routing, or
  its Prometheus rules.
- Retiring `image_prune`'s report to stdout, or changing what any periodic job does.

## Decisions

### 1. An external heartbeat observer, not a GitHub-native notification

Each periodic job pings a check of its own on success, and that check's `/fail` endpoint on
failure. The observer alarms when a check goes quiet for longer than its configured period
plus grace.

The property that decides this: **a failed run and a run that never happened are
indistinguishable to the observer, and both alert.** No other candidate has it. It is also
the only shape in which "the job was disabled" — the mode the 60-day rule makes likely for
a quiet company repository — produces a signal at all.

The service is Healthchecks.io, which this project already runs for the platform stack's
dead-man's-switch (*External Dead-Man's-Switch Heartbeat*,
`openspec/specs/iac-platform-services/spec.md`). Adding a second *use* of an incumbent
service costs no new vendor, no new account and no new bill.

### 2. Not a watcher workflow

The obvious cheap alternative is one scheduled workflow that queries the Actions API for
failed or missing runs of the others. It covers both failure modes for every workflow
except itself — and it is itself schedule-triggered, so it inherits the 60-day disable and
every other silence it exists to detect. Its own failure is indistinguishable from a quiet
week. The regress only terminates at an observer outside GitHub, which is Decision 1.

### 3. Not the host's own metrics pipeline (entry 15's sketch is not taken)

Entry 15 proposed closing the host half with node-exporter's textfile collector: a
`--collector.textfile.directory` flag, a mount, the prune writing a `.prom` file, and a
Prometheus staleness rule. That design has one genuine advantage over Decision 1 — the
threshold at which silence becomes an alarm would be a committed, reviewable line in
`platform/docker-compose.yml` rather than a setting at a vendor.

It is not taken, for three reasons:

- It closes the host half only. The continuous-integration half would still need Decision
  1, or an ingress path from GitHub's runners to the host's Prometheus — which means
  exposing a push endpoint on a host whose monitoring is currently reachable only over the
  tailnet. Two mechanisms for one problem is what folding entry 15 into this change was
  meant to avoid.
- It makes the host's own observability depend on the host. A prune alarm that is silent
  because the host is down is not wrong, exactly — the Watchdog covers that case — but it
  means the mechanism cannot report the one failure that matters most about it.
- It is four moving parts (flag, mount, writer, rule) against one `ExecStopPost=` line.

The advantage it gives up — an in-tree threshold — is recorded honestly in Risks below,
and is the main cost of this change.

### 4. One ping key, one slug per job, and the slug is a literal in the committed file

Healthchecks.io addresses a check either by an opaque per-check UUID URL or by
`https://hc-ping.com/<ping-key>/<slug>`, where the ping key is per project (verified
against the vendor's HTTP API documentation on 2026-09-09; the same page documents
`/fail`, `/start`, `/<exit-status>` and the `?create=1` parameter).

The slug form is chosen because it collapses N secrets into one and, more importantly,
puts a **per-job literal into the committed file**. That is what makes the coverage
assertion in Decision 8 a static read rather than an impossible one: a workflow's slug can
be compared against its own filename by a test that opens the file, and no test can compare
opaque UUIDs held in secrets against anything.

**Each slug is therefore a pure function of the reporter's own filename**, so the test
derives what it expects rather than consulting a second list that can drift from the first:

| Reporter | Slug | Derivation |
|---|---|---|
| `.github/workflows/drift.yml` | `infrastructure-drift` | `infrastructure-` + the workflow filename's stem |
| `.github/workflows/pre-commit-autoupdate.yml` | `infrastructure-pre-commit-autoupdate` | as above |
| `prune-host-images.service` | `<inventory_hostname>-prune-host-images`, so `main-server-prune-host-images` today | the inventory host's name + the unit's stem |

A committed workflow→slug map would work too and reads better at the vendor, but it is a
second place for the mapping to live and therefore a second place for it to drift. The
derivation has nothing to maintain: a slug that does not match its own filename fails the
test, which is what catches the failure that distinctness alone does not — `drift.yml`
carrying the autoupdate slug, so that two checks silently swap meaning while both stay
green.

The `infrastructure-` prefix is this repository's name. The host segment is **templated
from `inventory_hostname` rather than written as a literal**: this role is meant to be run
against a second host, and two hosts sharing one check would mean the live host's weekly
success keeps the check green while the other host's timer is dead — a silent violation of
the delta's own distinctness clause, arriving on the day a second host is added rather than
on the day someone reads this table. Templating makes the collision unreachable instead of
documented. The derivation is unchanged and still statically checkable: what the test reads
is the template's shape.

The free tier allows 20 checks; three reporters plus the existing Watchdog is four.

### 5. `?create=1`, deliberately, so a missing check is never silent

A slug-addressed ping to a check that does not exist returns 404 and does nothing. That
failure mode is the worst one available here: the reporter believes it is reporting, the
observer has nothing to go quiet, and the whole mechanism is decorative. `?create=1` makes
the observer create the check on first ping instead.

**`?create=1` goes on every ping URL this change writes — success and `/fail`, on all three
reporters — not on the success path alone.** The vendor documents the parameter for
slug-addressed success, `/start`, `/fail`, `/log` and `/<exit-status>` endpoints alike
(verified against its HTTP API documentation on 2026-09-09). Putting it only on success
would leave the case that matters most uncovered: a prune that fails from its very first
activation never takes the success path, so its check would never come into existence, its
`/fail` pings would 404, and a chronically failing unit would be reported by nothing at
all.

The cost is that an auto-created check carries the vendor's default period and grace rather
than the ones this design intends, so a weekly job would alarm daily until someone corrects
it. That is the safe direction to fail in: a wrong alarm is loud and gets fixed, a missing
check is silent forever. The intended values are recorded in the bootstrap documentation
and confirmed as part of this change's own confirm gate.

The alternative — pre-creating all three checks by hand and dropping the parameter — buys
correct periods from the first ping and gives up exactly this guard: a mistyped slug would
then 404 into silence rather than announcing itself as a spurious extra check.

### 6. A repository-scoped secret, never an Environment secret

`PLATFORM_SLACK_WEBHOOK_URL` and `PLATFORM_DEADMANSWITCH_URL` both exist already — and both
are `production` Environment secrets. A job that reads them must declare
`environment: production`, which is gated on required-reviewer approval. An alarm that
waits for a human to approve its own delivery is not an alarm.

So the ping key is a new **repository-scoped** secret, `HEARTBEAT_PING_KEY`, and the
reporting job declares no environment. This also keeps the reporting job inside the
existing rule that no unapproved job may hold production credentials: a ping key can create
and ping checks in one Healthchecks.io project and can do nothing else.

### 7. The report is emitted by a final job that always runs, and cancellation reports nothing

```
 ┌────────┐  ┌────────┐        ┌──────────────────────────┐
 │ job A  │─▶│ job B  │───────▶│ report:                  │
 └────────┘  └────────┘        │  needs: [A, B]           │
      │ fails                  │  if: always()            │
      └───────────────────────▶│  success → /<slug>       │
                               │  failure → /<slug>/fail  │
                               │  cancelled → nothing     │
                               └──────────────────────────┘
```

`needs:` over every other job plus `if: always()` is what makes an early failure report
immediately rather than falling through to the silence timeout hours or days later.

**The discriminator is `contains(needs.*.result, 'failure')`, not `success()`.** With
`if: always()`, `success()` is false whenever any needed job was *skipped* — and a skipped
job is the ordinary shape of a conditional step on a healthy run. A reporter keyed on
`success()` would therefore ping `/fail` on a perfectly healthy nightly, which is the one
outcome that would destroy this mechanism's credibility fastest: an alarm that fires when
nothing is wrong is ignored within weeks, and this change exists because an alarm was
ignored. Failure is reported when a needed job actually failed; a run containing skipped
jobs and no failures reports success.
Cancellation is an operator's act, not a defect; reporting it as failure would train the
alarm to be ignored, and the silence timeout still catches a run that is cancelled every
time.

The ping step itself checks its own HTTP status. A ping that does not return 2xx fails the
job — which is visible in the same red-run channel this change exists to distrust, but is
strictly better than discarding the only evidence that reporting is broken.

It also checks that the secret is non-empty **before** building the URL, and fails naming
it. An absent `HEARTBEAT_PING_KEY` expands to the empty string, which would otherwise
produce a malformed URL and a `curl` error — a red scheduled run whose cause is legible
only to someone already reading the log, which is this change's own subject reproduced
inside it. The window in which that can happen is between merge and the operator creating
the secret, which is why `tasks.md` sequences the secret before the pull request merges
rather than after.

A manual `workflow_dispatch` pings the same check as a scheduled run. That is deliberate —
it is what makes the confirm gate observable in minutes rather than in a week — but it has
a consequence worth stating: README's documented recovery for a disabled workflow is a
manual dispatch, and that dispatch resets the silence timer. An operator who dispatches
without also re-enabling the schedule buys up to one full period of false quiet from the
very alarm that told them to act. The runbook says so at the point of use; restricting the
ping to `github.event_name == 'schedule'` would close it, at the price of making every
verification of this mechanism wait for the next scheduled run — up to seven days for the
weekly check.

### 8. The coverage assertion lives in `.github/tests`

`test_ci_configuration.py` already enumerates schedule-triggered workflows (`triggers()`,
used by `TestScheduledHookRefresh`). The new assertion walks the same set and requires each
workflow to carry a reporting step addressing a slug of its own. This is a static read of a
committed file, which is exactly what that suite is for, and it is the part of this change
that survives everyone forgetting the change happened.

What the assertion cannot establish, and must not be read as establishing: that the secret
exists, that the check exists at the vendor, or that its period is right. Those are
Decision 5's and the confirm gate's business.

### 9. Host side: the init system reports, not the script

`prune-host-images.service` gains an `ExecStopPost=` that invokes a root-owned, `0700`
reporting script; the script sources `/etc/prune-host-images/heartbeat.env` (mode `0600`,
root), rendered by Ansible from a Vault-encrypted variable.

**The script, rather than a `curl` written directly into `ExecStopPost=`.** A command line
is readable from `/proc/<pid>/cmdline` by any local account for as long as the process
runs, and this host deliberately carries unprivileged operator accounts
(*Unprivileged Operator Accounts Support Interactive Host Inspection*,
`openspec/specs/iac-host-configuration/spec.md`). Expanding the ping key into argv would
defeat the `0600` file it was just read from during exactly the window the ping is in
flight. The script keeps the key in its environment and hands the URL to `curl` off the
command line.

**The branch is on `$SERVICE_RESULT`, not on `$EXIT_STATUS`.** systemd sets
`$EXIT_STATUS` to a *signal name* — `KILL` — when the process was killed rather than
exited, which is precisely the `TimeoutStartSec` path this decision exists to cover; any
construction treating it as a number breaks there and only there, which is the worst place
for a bug to hide. `$SERVICE_RESULT` is `success` or one of a set of failure words, and
that is the discriminator. `$EXIT_STATUS` is carried through as diagnostic text in the
ping body, where its being a signal name is an advantage rather than a defect.
`ExecStopPost=` runs no shell of its own, so the reporting script is invoked directly and
does its own branching.

It must come from systemd rather than from `prune-host-images` itself for the same reason
`image_prune_timeout_start_sec` is the unit's bound rather than a `timeout` inside the
script — the role's own defaults say it: "systemd records the expiry and marks the unit
failed from outside the process, which is where a report about a killed region has to come
from." A script killed by its own timeout cannot report that it was killed. That case —
rc 137 with empty output, the container runtime having stopped answering — is precisely
what the bound exists for and precisely what must reach the alarm.

`ExecStopPost=` runs on every exit path, including the timeout kill, which is why it is
used in preference to `OnFailure=` (failure only) or `ExecStartPost=` (success path only).

**The obligation covers units this repository defines, not every timer on the host.**
Ansible installs unattended security updates, which ship timers of their own; those are the
packager's to define, bound and report, and this repository neither writes nor owns them.
Writing the requirement over "every scheduled unit Ansible installs" would oblige a
reporter this change does not build and no test asserts — an obligation the tree does not
meet from the day it is archived.

**The reporting is bounded, its own failure is ignored, and it says so in the journal.** The ping carries a
`--max-time` and a bounded retry, because a `curl` that hangs inside `ExecStopPost=` holds
the unit in `deactivating` until `TimeoutStopSec` — on the very path a hung container
runtime already put it, so the reporting would compound the fault it exists to announce.
And the command is prefixed with `-`, so a failed ping does not mark a successful prune's
unit failed: a prune that did its work correctly must not be recorded as having failed
because a third-party endpoint was briefly unreachable. The consequence is deliberate and
is the mechanism working as designed — an unsent ping becomes silence, and silence is what
the observer alarms on. The failure is not swallowed; it is routed to the alarm this whole
change builds, instead of to a failed-unit state that nothing reads.

It is still written down locally. The script reports the endpoint it tried and `curl`'s
status on stderr, which `ExecStopPost=` journals — otherwise an operator answering a
`main-server-prune-host-images` alarm nine days later finds a successful unit, a successful
prune, and no trace anywhere of why the report never arrived. The CI half makes the same
failure legible by failing the reporting job; the host half cannot do that without lying
about the prune, so it makes it legible in the journal instead.

### 10. Routing: these checks alert to Slack, the Watchdog keeps its out-of-band destination

`docs/bootstrap-a-new-host.md` says of the Watchdog's destination: "ideally somewhere other
than the same Slack workspace: this is the alarm for when everything else is down." That
separation is the whole value of that alarm and a weekly CI failure must not erode it.

The three new checks route to Slack `#alerts` — the destination that already carries
routine platform alerts and is read as such. Both routings are provider-side configuration,
so both are recorded in the bootstrap documentation rather than in the tree.

### 11. Period and grace are set against observed scheduling, not against the cron line

`drift.yml` declares `cron: "0 3 * * *"` and its last eight scheduled runs started between
07:21 and 08:15 UTC — a consistent delay of over four hours, which is GitHub's queue
behaviour and not a defect. A tolerance derived from the declared minute would alarm on a
healthy system, and an alarm that fires on healthy systems is the failure mode this whole
change is trying not to reproduce.

| Check | Period | Grace |
|---|---|---|
| `infrastructure-drift` | 1 day | 12 hours |
| `infrastructure-pre-commit-autoupdate` | 7 days | 2 days |
| `main-server-prune-host-images` | 7 days | 2 days |

The host unit's own `image_prune_randomized_delay_sec` is one hour, comfortably inside a
two-day grace.

### 12. The reporter's base URL is a role variable, so a scenario can observe a report

`https://hc-ping.com` is a default in `ansible/roles/image_prune/defaults/main.yml`, not a
literal in the unit.

**Every scenario the role has sets it to a local sink, not only the ones asserting on
reports.** A scenario that activates the unit under the production default would ping the
vendor from a hosted runner and, with `?create=1`, create a check there — on every pull
request touching `ansible/`. The role's existing scenarios activate the unit, so this is
not hypothetical, and "the reporting scenarios use a sink" is a constraint on one scenario
mistaken for a property of all of them. A static assertion over the scenarios' own
variables is what makes it a property.

The production default stays `https://hc-ping.com` rather than being made a second required
input: one required input (the ping key, Decision 13) already fails a misconfigured host
loudly, and a second adds a thing every caller must supply to buy nothing the assertion
does not.

Without that seam, the host delta's scenarios cannot be verified at all. Molecule is the
only mechanism that can observe what the role *does*, and a scenario asserting "a unit
killed by its bound reports a failure" would otherwise have to either carry a real ping key
or point a dummy one at the vendor — a network call and a vendor-side check creation from a
hosted runner on every pull request touching `ansible/`, which the Molecule tier's own
no-credential obligation forbids. With the variable, a scenario points the reporter at a
local sink and asserts on what arrived.

This is the same shape as the stubbed-runtime rig `docs/change-queue.md` entry 17 already
wants adopted for this role's two unreachable guards: supply the seam, then assert through
it. That entry is not closed here — this seam serves the reporter only.

### 13. An absent report address fails the role by name

`image_prune` gains a required input with no default, which is the class
*A Role's Absent Required Input Is Reported by Name*
(`openspec/specs/iac-host-configuration/spec.md`) governs: the role asserts it before
touching the host and fails naming it.

The alternative — tolerate absence and silently skip the reporting, as the GHCR credential
path does — is wrong here. A registry credential's absence is a legitimate operating mode
for a host that pulls no private images; an absent reporting address produces a prune that
runs unobserved, which is the exact state this change exists to end. The failure it would
otherwise produce is this change's own subject, arriving quietly.

## Risks / Trade-offs

- **The threshold that decides "silence" is not in the tree.** This is the real cost of
  Decision 3, and it cannot be mitigated away — only documented (Decision 11's table, into
  `docs/bootstrap-a-new-host.md`) and confirmed once (the confirm gate). A future edit at
  the vendor that widens a grace to 30 days passes every check in this repository.
- **A vendor outage is a silent failure of the alarm itself.** Healthchecks.io going down
  produces no alert about the alert. This is already accepted for the platform Watchdog and
  is not made materially worse by three more checks.
- **`?create=1` can mask a typo.** A misspelled slug auto-creates a *second* check that
  goes green forever while the intended one goes quiet — so the quiet one still alarms, and
  the symptom is a spurious extra check rather than silence. The coverage test derives each
  workflow's expected slug from its own filename (Decision 4), so a misspelling in the tree
  fails the pull request; a slug misspelled identically in the tree and at the vendor is
  caught by the confirm gate and by nothing after it.
- **A manual dispatch resets the silence timer.** README's recovery for a disabled workflow
  is a `workflow_dispatch`, and that run pings success — so dispatching without re-enabling
  the schedule buys up to one period of false quiet (1 day for drift, 7 for autoupdate) at
  the moment an operator is acting on the alarm. Bounded, recoverable, and called out in
  the runbook at the point of use; Decision 7 records why the ping is not restricted to
  scheduled events.
- **The ping key is a suppression capability.** Anyone holding it can report success on a
  job's behalf. It is treated as a secret on both sides for that reason — a repository
  secret in CI, a `0600` file plus a `0700` script on the host, never expanded into a
  command line (Decision 9) — but it is worth being clear that its risk is suppression, not
  data access.
- **The host half's coverage assertion is weaker than the CI half's.** A future
  Ansible-installed timer can be merged without a reporter unless something checks. The
  static suite gains that assertion (`tasks.md` 4.7), but it has to read units this
  repository writes inline in a role's `tasks/main.yml` rather than under `templates/`,
  which is a shakier read than the workflow one and will need revisiting if a role ever
  templates its units instead.
- **A check that has never been pinged cannot go quiet.** Under Decision 5 a check comes
  into existence at its first ping, so a reporter that is merged and then never runs even
  once — a scheduled workflow added while the repository is inactive enough for GitHub to
  disable it, a timer that never fires after install — leaves nothing at the vendor to
  alarm on. The coverage test establishes that a reporter exists in the tree, not that its
  check exists at the vendor. This change's own confirm gate closes the gap for the three
  reporters it ships; a reporter added later inherits it, and the goal "a scheduled
  workflow added later cannot be merged unmonitored" holds from that reporter's first
  successful ping onward rather than from its merge.
- **Three more alerts into `#alerts`.** If a periodic job becomes chronically red, this
  will be noisy. That is the intended behaviour, and the fix is to repair the job, not to
  widen the grace.

## How this change is confirmed

A healthy deploy is not this change working. What proves it:

1. `workflow_dispatch` both scheduled workflows; both checks report and go green at the
   vendor, and the runs stay green.
2. `curl` the `/fail` endpoint of one check by hand; a Slack `#alerts` message arrives.
   This proves the routing, which no test can.
3. `systemctl start prune-host-images.service` on the host; `main-server-prune-host-images`
   reports.
4. The silence path, which is the whole point and the slowest to observe: create a scratch
   check with a five-minute period, ping it once, and let it lapse. An alarm arrives without
   any job having failed. Delete the scratch check afterwards.
5. Read back each of the three checks' period and grace against Decision 11's table, since
   Decision 5 lets a check exist with the wrong ones.
