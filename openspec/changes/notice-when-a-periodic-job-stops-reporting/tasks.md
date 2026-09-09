## 0. A note on citations in the files this change writes

Tasks below write rationale into files **outside** `openspec/` — two workflows,
a role's `README.md` and `defaults/main.yml`, `README.md`, and
`docs/bootstrap-a-new-host.md`. This project's citation rule binds there, and
`.github/tests/test_ci_configuration.py` catches only the *path* form of a
violation. Where such a file points at reasoning that lives only inside this
change, write **the change's name and the artifact's name, in prose, with no
path** — "the change `notice-when-a-periodic-job-stops-reporting`, `design.md`
Decision 9". Requirements are cited the other way:
`openspec/specs/iac-cicd-pipeline/spec.md` plus the requirement's own name.

Inside this change's own artifacts, a bare "Decision 9" is a sibling reference
and is fine.

## 1. Prerequisites the operator performs

These are not code, and the change cannot be confirmed without them. 1.1 and 1.2
SHALL be complete **before the pull request merges**, not after: a merged
reporter whose secret does not exist expands it to the empty string and turns the
scheduled run red, which is this change's own subject reproduced inside it. Task
2.5 makes that failure legible if it happens anyway; the sequencing is what
prevents it.

- [ ] 1.1 At Healthchecks.io, in the same project the platform Watchdog uses,
  create a **project ping key** and add it as a **repository-scoped** GitHub
  Actions secret named `HEARTBEAT_PING_KEY`. Not an Environment secret — Decision 6
  says why, and task 4.4 asserts the job declares no `environment:`.
- [ ] 1.2 Add the same value to `ansible/inventory/group_vars/prod.yml` as a
  Vault-encrypted variable for the host reporter (task 3.1), keeping the plaintext
  out of version control per *Secrets Never Committed in Plaintext and Never Left
  World-Readable on Host* (`openspec/specs/iac-host-configuration/spec.md`).
- [ ] 1.3 Configure the three checks' alert destination to Slack `#alerts`, and
  confirm the existing Watchdog check still alerts to its separate out-of-band
  destination — Decision 10. Checks themselves need not be pre-created: Decision 5
  has the reporters create them on first ping, on **every** ping path.

## 2. Continuous-integration reporters

Slugs are derived from the workflow's own filename, per Decision 4:
`drift.yml` → `infrastructure-drift`, `pre-commit-autoupdate.yml` →
`infrastructure-pre-commit-autoupdate`. Task 4.2 asserts that derivation, so a
slug chosen freely here will fail the build.

- [ ] 2.1 Add a `report` job to `.github/workflows/drift.yml`: `needs:` every other
  job in the workflow, `if: always()`, no `environment:`, and `permissions: {}` —
  the job needs no scopes at all. The success/failure discriminator is
  `contains(needs.*.result, 'failure')`, **never `success()`**: under
  `if: always()`, `success()` is false whenever a needed job was merely *skipped*,
  which is the ordinary shape of a healthy run, and a reporter keyed on it would
  ping `/fail` on a healthy nightly (Decision 7). On a successful workflow result it pings
  `https://hc-ping.com/$KEY/infrastructure-drift?create=1`; on failure it pings
  `https://hc-ping.com/$KEY/infrastructure-drift/fail?create=1`; on `cancelled()`
  it pings nothing (Decision 7). **`?create=1` on both URLs** — the vendor honours
  it on `/fail` as well as on success, and omitting it there is the failure
  Decision 5 exists to prevent. The step SHALL fail if the ping does not return
  2xx: `curl --fail --silent --show-error --retry 3`.
- [ ] 2.2 The same job in `.github/workflows/pre-commit-autoupdate.yml`, slug
  `infrastructure-pre-commit-autoupdate`.
- [ ] 2.3 Give each reporting step a comment naming what it is for and what it is
  *not*: that silence, not the ping, is what raises the alarm; that the vendor-side
  period and grace are not readable from this file, with the bootstrap document
  named as where they are recorded; and that a manual dispatch resets the silence
  timer (Decision 7).
- [ ] 2.4 Confirm the `drift.yml` reporter does not disturb the existing drift-issue
  step: a drift-found run exits 0 today and must keep reporting *success* — this
  change reports whether the run happened and worked, never what it found
  (`design.md` Non-Goals).
- [ ] 2.5 Before building either URL, the step SHALL fail with a message naming
  `HEARTBEAT_PING_KEY` when that secret is empty, rather than letting an empty
  expansion become a malformed URL and a bare `curl` error (Decision 7).

## 3. Host reporter

Slug `{{ inventory_hostname }}-prune-host-images` — `main-server-prune-host-images`
on this host — templated rather than written as a literal, so two hosts converged
by this role cannot share one check and mask each other's silence (Decision 4).

- [ ] 3.1 In `ansible/roles/image_prune/defaults/main.yml`, add
  `image_prune_heartbeat_base_url` defaulting to `https://hc-ping.com`
  (Decision 12 — this is the seam the role-behaviour tests need) and
  `image_prune_heartbeat_ping_key` with **no** default, each with a comment saying
  why. Render the key into `/etc/prune-host-images/heartbeat.env` (owner `root`,
  mode `0600`) from the Vault variable of 1.2.
- [ ] 3.2 Give the role the named-input assertion for
  `image_prune_heartbeat_ping_key`, in the established form and before any task
  changes the host, per *A Role's Absent Required Input Is Reported by Name*
  (`openspec/specs/iac-host-configuration/spec.md`) and Decision 13. `deploy_apps`
  in this same role is the pattern to follow.
- [ ] 3.3 Install a root-owned `0700` reporting script that sources
  `heartbeat.env` and pings `<base_url>/<key>/<templated slug>` on
  success and `.../fail` on failure, `?create=1` on both. The URL SHALL NOT be
  passed on `curl`'s command line — `/proc/<pid>/cmdline` is world-readable and
  this host carries unprivileged operator accounts (Decision 9). The ping is
  bounded: `--max-time` and a bounded retry, so a hung endpoint cannot hold the
  unit in `deactivating` until `TimeoutStopSec` on the very path a hung container
  runtime already put it. `?create=1` on both URLs, as on the CI side. The script
  writes the endpoint it tried and `curl`'s status to stderr — `--show-error`, not
  silenced — so `ExecStopPost=` journals a ping that failed; task 3.4 makes that
  failure invisible to systemd, and the journal is then the only local trace an
  operator answering the resulting alarm has (Decision 9).
- [ ] 3.4 Add `ExecStopPost=` to the `prune-host-images.service` unit — written
  inline in `tasks/main.yml` via `copy:`/`content:`, which is the shape this
  repository's units already take and the shape task 4.7 asserts against; do not
  convert it to `templates/`. Prefix the command with `-` so a failed ping does not
  mark a successful prune's unit failed: the unsent ping becomes silence, and
  silence is what the observer alarms on (Decision 9). It branches on **`$SERVICE_RESULT`** (`success` versus
  anything else), never on `$EXIT_STATUS`, which systemd sets to a *signal name*
  (`KILL`) on the `TimeoutStartSec` path — the one path this reporting exists for.
  `$EXIT_STATUS` is carried as diagnostic text in the ping body only.
  `ExecStopPost=` rather than `OnFailure=` or `ExecStartPost=`, because only it
  runs on every exit path including that kill (Decision 9).
- [ ] 3.5 The reporting change SHALL NOT cause the unit to run. Installing or
  updating it triggers no prune, per *Unreferenced Host Images Are Pruned on a
  Schedule* (`openspec/specs/iac-host-configuration/spec.md`) and the added
  requirement's own scenario.
- [ ] 3.6 Update **every existing** `image_prune` Molecule scenario — `default` and
  `abandon-paths` — to supply `image_prune_heartbeat_ping_key` and to set
  `image_prune_heartbeat_base_url` to a local sink. Both are breaking for those
  scenarios as they stand: 3.2 makes the key required, and any scenario that
  activates the unit under the production default would ping the vendor from a
  hosted runner and create a check there on every pull request touching `ansible/`
  (Decision 12). This is not optional cleanup — without it `molecule test --all`
  is red on the first run for a reason the rest of this list does not explain.
- [ ] 3.7 Record in `ansible/roles/image_prune/README.md` what the reporter is, the
  slug it uses, that the vendor-side period and grace are documented in
  `docs/bootstrap-a-new-host.md`, that a silent check is the alarm rather than a
  red unit, that the slug is templated per host so a second converged host gets a
  check of its own rather than sharing this one, and that removing the ping key
  input breaks convergence by design.

## 4. Tests

Derived from the delta specs by an author other than the implementer, before
implementation, per this project's workflow. Two of this project's three test
commands apply; the Terraform row does not.

- [ ] 4.1 Dispatch the test author with the `.github/tests` row —
  `python3 -m unittest discover --start-directory .github/tests`, glob
  `.github/tests/*.py` — for every property that is a static read of a committed
  file, and separately with the Molecule row —
  `molecule test --all` from the role directory, scenarios under
  `ansible/roles/image_prune/molecule/<scenario>/` — for what the role converges
  to on a host.
- [ ] 4.2 `.github/tests`: **every** workflow whose triggers include `schedule`
  carries a reporting step, and the slug it addresses equals `infrastructure-`
  plus that workflow file's own stem. The **derivation**, not merely distinctness:
  distinctness alone passes a `drift.yml` carrying the autoupdate slug, which
  leaves two checks silently swapped and both green (Decision 4).
- [ ] 4.3 `.github/tests`: the reporting job depends on every other job in its
  workflow and is conditioned to run on failure as well as success — a reporter
  that only runs on the success path is the defect this asserts against — and its
  failure branch is keyed on a needed job having **failed**, not on `success()`
  being false, which a merely skipped job also produces (Decision 7).
- [ ] 4.4 `.github/tests`: no reporting job declares an `environment:`, and the
  secret it reads is not one of the `PLATFORM_*` Environment secrets (Decision 6).
- [ ] 4.5 `.github/tests`: the cancellation path reports nothing, and every ping
  URL a workflow carries — success and `/fail` alike — sets `create=1`
  (Decision 5).
- [ ] 4.6 `.github/tests`: the slugs of **every reporter it discovers** — each
  schedule-triggered workflow's and each timer-installing role's — are pairwise
  distinct, which is the host delta's distinctness clause and reaches across the
  two halves of this change as no single-role test can. Quantify over what
  discovery finds rather than naming today's three, and fail when discovery finds
  no subject, for the reason task 4.7 gives.
- [ ] 4.7 `.github/tests`: every role that installs a `.timer` unit also installs
  a service unit carrying a reporter. Note for the author: this repository writes
  its units **inline in `tasks/main.yml`** via `copy:`/`content:`, not under
  `templates/` — assert against that shape. The test SHALL **fail when its
  discovery finds no subject at all** rather than passing vacuously: a role that
  later templates its units would otherwise leave this universal assertion
  quantified over an empty set, and green. *Ansible Configuration Is Verified in
  Continuous Integration and Gates the Merge*
  (`openspec/specs/iac-cicd-pipeline/spec.md`) already requires exactly that of
  Molecule role discovery and is the precedent; task 4.2's workflow discovery
  carries the same obligation. Record the shape in the test's own docstring too,
  so the reason for the discovery rule survives the next reader.
- [ ] 4.8 Molecule, `image_prune`: after convergence the unit carries
  `ExecStopPost=` invoking the reporting script; the script is `0700` root-owned;
  `/etc/prune-host-images/heartbeat.env` is `0600` root-owned; and converging again
  performs no prune.
- [ ] 4.8a `.github/tests`: the reporting script's committed text passes the URL to
  `curl` off the command line (`--config`, stdin or equivalent), and **no argument
  on the `curl` invocation carries or expands to the URL or the ping key — neither
  a literal nor a variable reference**. Asserting the absence of a literal alone is
  not enough: `curl "$PING_URL"` contains no literal and puts the key in
  `/proc/<pid>/cmdline` exactly as Decision 9 forbids. Assert in the same place
  that both URLs the script builds carry `create=1` — Decision 5 calls the missing
  check "the worst one available here" and names the chronically failing prune as
  its example, and that third of the mechanism is otherwise guarded by nothing.
  Assert in the same place that the script writes the attempted endpoint and
  `curl`'s status to stderr with `--show-error` rather than silencing it: task 3.4
  makes a failed ping invisible to systemd deliberately, so that write is the only
  local trace of it and is what the host delta's undeliverable-report scenario
  obliges.
- [ ] 4.8b `.github/tests`: no `image_prune` Molecule scenario leaves
  `image_prune_heartbeat_base_url` at its production default, and every one supplies
  a ping key (3.6). A scenario's own variables are a static read of a committed
  file, and this is what turns "the reporting scenarios use a sink" into a property
  of all of them. Note for the author: this role's scenarios pass role variables in
  the `Converge` play's `vars:` block in `converge.yml` — that is the file 3.6 sets
  them in and the file this assertion reads. Fail when discovery finds no scenario,
  for the reason task 4.7 gives: a renamed or relocated scenario directory would
  otherwise leave this universal quantified over an empty set, and task 4.11's
  no-vendor-contact claim rests on this assertion.
- [ ] 4.9 Molecule, `image_prune`, through the base-URL seam of 3.1 pointed at a
  local sink: a successful activation reports success; a unit whose script exits
  non-zero reports a failure; and a unit killed on `TimeoutStartSec` expiry — the
  empty-output case — reports a failure too. Where the timeout case cannot be
  reached deterministically, say so in `test-plan.md` rather than approximating it
  with a sleep.
- [ ] 4.10 Molecule, `image_prune`: converging with no ping key supplied fails
  naming that input, before the host is changed (3.2, Decision 13).
- [ ] 4.11 The static suite must stay inside its stated constraints: no network
  call, no credential, no container runtime and no Terraform binary in
  `.github/tests`. The reporters' URLs are asserted as text, never requested — and
  no `image_prune` scenario reaches the vendor, which is a property of all of them
  by 3.6 and is held there by 4.8b — not an inference from 4.9's sink alone.

## 5. Documentation

- [ ] 5.1 `README.md`: extend the runbook section that covers re-enabling the
  drift workflow to say that a scheduled workflow no longer runs silently — what
  the alarm looks like, where it arrives, that a check going quiet is the signal,
  and a pointer to Appendix A, which task 5.2 makes the single place carrying the
  slugs and their period and grace — a pointer, not a second copy of the table,
  which is what the added requirement's own wording asks for. Include
  the dispatch caveat: a manual `workflow_dispatch` resets the silence timer, so
  after one, confirm the schedule itself is enabled rather than reading the green
  check as evidence.
- [ ] 5.2 `docs/bootstrap-a-new-host.md`: add `HEARTBEAT_PING_KEY` to the Appendix A
  secret inventory (repo secret, created in the same stage as the Watchdog, "breaks
  when wrong: nothing notices a periodic job stopping"), and record the three
  checks with Decision 11's period and grace values **in Appendix A alongside that
  secret** — one location, which is where the added requirement points and where
  task 5.1's pointer lands. The stage-7 heartbeat step references Appendix A rather
  than restating the values.
- [ ] 5.3 `docs/bootstrap-a-new-host.md`: the "What to change for a company host"
  appendix — the slug prefixes are this repository's name and this host's, so a
  second host and a second repository each need their own.

## 6. Verification and rollout

- [ ] 6.1 Provision the working tree before reading any verification result:
  install the pinned toolchains from `.github/requirements-ci.txt` and
  `ansible/requirements-test.txt`, and the pinned Galaxy content from
  `ansible/requirements.yml`. A suite that cannot reach what it needs skips and
  reports success — until provisioning is complete, report verification as not run.
- [ ] 6.2 Run `python3 -m unittest discover --start-directory .github/tests` from
  the repository root, and `molecule test --all` from `ansible/roles/image_prune/`.
  Read Molecule's SCENARIO RECAP and confirm it names **every** scenario the role
  has: `--all` stops at the first failure and silently skips the rest.
  Coordinate before running Molecule — its container name and ephemeral directory
  are shared across working trees (`AGENTS.md`, "Testing").
- [ ] 6.3 Run `pre-commit run --all-files` and confirm `ansible-lint`,
  `ansible-playbook --syntax-check` and `gitleaks` pass. `gitleaks` matters
  particularly here: this change adds a URL-shaped secret to two workflows and a
  role.
- [ ] 6.4 Dispatch `ai-toolkit:change-code-reviewer` over the diff once 6.2 and 6.3
  pass.
- [ ] 6.5 Confirm tasks 1.1 and 1.2 are done before the pull request merges, then
  open it, let CI run, and wait for the operator's confirmation that it merged and
  that the deploy is healthy. Nothing here applies to production from a local
  machine.
- [ ] 6.5a The host half does not reach the host by merging. No workflow converges
  `ansible/` — that is queue entry 23, which is not this change — so after the merge
  the operator runs `ansible-playbook playbooks/host-baseline.yml` against prod, as
  `docs/bootstrap-a-new-host.md` describes, supplying the Vault password and the new
  ping key of 1.2. Until that converge has happened, 6.6's host steps are testing
  the old unit and reporting nothing; do not read their silence as a defect in the
  observer.
- [ ] 6.6 Confirm the effect, per `design.md`'s "How this change is confirmed": both
  workflows dispatched and reporting; a hand-sent `/fail` arriving in Slack
  `#alerts`; the host unit started manually and reporting; a scratch five-minute
  check left to lapse to prove the silence path alarms at all; and each check's
  period and grace read back against Decision 11's table. Record the results in this
  change's artifacts.

## 7. Archive

- [ ] 7.1 Once the effect is confirmed, bring the branch back to the freshly
  fetched trunk and commit the specification record, then open the record's own
  pull request.
- [ ] 7.2 In the same commit, delete `docs/change-queue.md` entries 32 and 15 — both
  are delivered here — and leave entry 16 (*report refused removals in the host
  prune*) untouched: it is about what the prune's report says, not about whether
  anyone sees that the prune ran. Entry 17 (*the stubbed-runtime rig*) also stays:
  task 3.1's base-URL seam serves the reporter only and closes neither of the two
  guards that entry names.

Branch and working-tree removal happen after that pull request merges, which is
after the commit this file lives in, so they are recorded here in prose rather
than as tasks that could never be ticked.
