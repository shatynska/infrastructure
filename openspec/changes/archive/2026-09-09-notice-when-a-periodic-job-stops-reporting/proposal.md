## Why

`pre-commit-autoupdate.yml` failed on three consecutive scheduled runs — 2026-08-24, 2026-08-31, 2026-09-07 — with the same error each time. Each run was red in the Actions tab and each sent GitHub's own failure email. Three weeks passed and nothing acted. `open-autoupdate-pr-with-app-token` removed the cause of those three failures and, in its own words, added none; it did not touch the silence around them, and named that as a non-goal.

The silence is not a property of that workflow. Three periodic jobs run in this system and every one of them fails into it:

| Job | Schedule | What notices today |
|---|---|---|
| `drift.yml` | nightly | an issue **when drift is found**; nothing when the run itself errors |
| `pre-commit-autoupdate.yml` | weekly | nothing |
| `prune-host-images.timer` on the host | weekly | a failed systemd unit nobody reads |

Two of them already had this written down as a known gap: *Scheduled Drift Detection* (`openspec/specs/iac-cicd-pipeline/spec.md`) says "a persistently red scheduled job is muted in practice" and acts on it only for the drift case, and `prune-unreferenced-host-images-periodically` left the same hole deliberately (`docs/change-queue.md` entry 15).

The mechanism was never missing; the **channel** was. GitHub delivered three failure emails to a mailbox with a measured read rate of zero. Any design whose terminus is "GitHub notifies someone" re-picks a channel this repository has already tested.

And there is a second failure mode that no failure-triggered alarm can reach: a job that **stops running at all** emits no failure event. GitHub disables schedule-triggered workflows after 60 days of repository inactivity — README already carries the manual re-enable procedure for exactly this — and a systemd timer that stops being scheduled leaves no failed unit behind. A red run and a run that never happened need to be equally loud, and today one of them is silent by construction.

## What Changes

- Every periodic job this repository defines — a schedule-triggered workflow, and a host unit whose definition one of its roles writes — reports its own liveness to the **external heartbeat service this project already runs** (Healthchecks.io), by pinging a check of its own on success and that check's `/fail` endpoint on failure. Silence for longer than the check's configured period is what raises the alarm, so a red run, a run killed mid-flight and a run that never started all alert identically.
- The observer is external by construction, which is what stops the regress: a watcher that is itself a scheduled workflow inherits every failure mode it was built to catch.
- Each job addresses its check by a **slug that is a literal in the committed file**, under a single repository-scoped ping key. One secret, not one per job — and a slug in the tree is a static read, so the assertion below is possible at all.
- `.github/tests` gains the assertion that **every** schedule-triggered workflow carries such a heartbeat. A scheduled workflow added later cannot be merged unmonitored.
- The two queued entries this closes — 32 (*notice a scheduled workflow that goes red*) and 15 (*alert when the host prune stops working*) — are delivered by one mechanism rather than two. Entry 15's own sketch (node-exporter textfile collector plus a Prometheus staleness rule) is not taken; `design.md` records why.
- Routing is configured at the provider so these checks reach Slack `#alerts`, **not** the out-of-band destination the host's Watchdog uses. `docs/bootstrap-a-new-host.md` made that destination deliberately separate — "this is the alarm for when everything else is down" — and a weekly CI failure must not erode it.

## Capabilities

### New Capabilities

None. Both obligations belong to capabilities that already exist.

### Modified Capabilities

- `iac-cicd-pipeline`: ADDED requirement — a schedule-triggered workflow reports its own liveness to an external observer, and that obligation is asserted statically by the suite *The Continuous-Integration Configuration Is Itself Verified* already mandates.
- `iac-host-configuration`: ADDED requirement — a scheduled unit whose definition one of this repository's roles writes reports its own liveness the same way, so that a unit that fails, is killed, or stops being scheduled is equally visible. Timers a package ships with — unattended security updates' among them — are the packager's to define and report, and are outside it.

## Impact

- `.github/workflows/drift.yml`, `.github/workflows/pre-commit-autoupdate.yml` — a final reporting job.
- `.github/tests/test_ci_configuration.py` — the coverage assertion over schedule-triggered workflows.
- `ansible/roles/image_prune/` — the unit reports its own exit status; its Molecule scenarios cover what the role converges to.
- `README.md` runbook and `docs/bootstrap-a-new-host.md` (stage 7 and the Appendix A secret inventory) — one new repository secret, and the provider-side checks it addresses.
- One new repository-scoped GitHub Actions secret, and one new Ansible Vault variable for the host-side unit. Neither may be an Environment secret: the `production` Environment is gated on required-reviewer approval, which an unattended alarm cannot wait for.
- `docs/change-queue.md` — entries 32 and 15 are deleted when this change is archived.
