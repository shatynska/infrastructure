## Why

`openspec validate --archived` exits non-zero on this repository, and has for
weeks. Nothing runs it, so nobody knew.

`docs/change-queue.md` entry 12 recorded three archived changes with unticked
tasks on 2026-09-08. Re-run the same command today and there are **four**:

| Change | Tasks |
|---|---|
| `2026-08-19-add-prod-data-volume` | 16/19 |
| `2026-09-04-fix-cadvisor-containerd-snapshotter` | 10/11 |
| `2026-09-07-reclaim-superseded-app-images` | 24/29 |
| `2026-09-08-refresh-readme-accuracy` | 50/51 |

The fourth was archived the same day the entry was written. The entry's own
argument — *a check that is already red cannot tell anyone when something new
goes wrong* — demonstrated itself inside twenty-four hours, against the person
making it. That is the case for this change, and it is not hypothetical.

### The entry's diagnosis is right about one of the four

The entry says each unticked box is "a verification task ... left unticked
rather than recorded as not done", leaving the record unable to distinguish
*this was verified* from *nobody said*. Read individually, the four are red for
four different reasons, and only one matches that description:

- **`add-prod-data-volume` 3.4, 3.5, 3.6** are dispositioned at length, in
  prose, on the task lines themselves — *"**Skipped by user decision** — never
  run locally (no `HCLOUD_TOKEN` in the authoring sandbox)"*, *"**Partially
  covered, not by this task**"*. Nothing is ambiguous. The author declined to
  tick a box for work that was not done, which is the honest act. The defect is
  that a checkbox has two states and the truth needs a third.

- **`fix-cadvisor-containerd-snapshotter` 2.3** is the entry's case exactly:
  *"`pre-commit`/`gitleaks` aren't installed in this dev environment"*. It is
  also the precise failure `AGENTS.md` now devotes a rule to — verification that
  cannot reach what it needs, reported as something other than a pass.

- **`reclaim-superseded-app-images` 4.1–4.5** are not verification tasks at all.
  They are a five-step operator rollout, and 4.4 is labelled in its own text
  *"the change's `ship:confirm` observation"*. That change was archived with its
  ship gate open and **no waiver recorded anywhere in its artifacts** — nine
  other archived changes do record one. This is a workflow breach, not
  bookkeeping.

- **`refresh-readme-accuracy` 8.6** is *"Remove the branch locally and on the
  remote, and remove the working tree"* — a step that happens **after** the
  archive commit that writes `tasks.md`. It cannot be ticked in the commit that
  records it. It is the only archived change that put this step in `tasks.md`,
  and the only one red for this reason.

### The evidence is not missing; it is filed against the wrong change

Three of the four are settleable from evidence that exists today.

`reclaim-superseded-app-images` recorded a baseline of 219 images, 46.43 GB,
42.88 GB reclaimable, 190 of them `commerce-ops`. `main-server`, read on
2026-09-08:

```
TYPE      TOTAL   ACTIVE   SIZE      RECLAIMABLE
Images    10      10       3.553GB   0B (0%)
```

with a single `ghcr.io/fuperia-it/commerce-ops` tag, and
`/usr/local/bin/app-deploy` present and carrying the `reclaim()` function. Tasks
4.1, 4.2 and 4.3 were performed, and 4.4's steady state is holding.

The repository already knew. `prune-unreferenced-host-images-periodically`, in
its own `design.md`, states *"one `ghcr.io/fuperia-it/commerce-ops` image today
against 190 before it"* — written the next day, one directory over, by the
successor change. The archived record is not ambiguous for want of evidence. It
is ambiguous because nothing carries evidence back to the claim it settles.

`refresh-readme-accuracy` 8.6 is likewise settled: no such branch exists locally
or on `origin`, and no such working tree exists. It was performed.

That window closes. Had this waited two months, the host would have told us
nothing, and three of these four would have become permanently unanswerable.

### Nothing runs the check

`openspec validate` appears in no workflow under `.github/workflows/` and in no
hook in `.pre-commit-config.yaml`. Nothing verifies that the specifications
parse, that a change's deltas are well-formed, or that an archived change's
tasks are complete. `.github/tests/test_ci_configuration.py` asserts a great deal
*about* `openspec/` — the citation-form rule runs to hundreds of lines — but it
never invokes the tool whose files those are.

The pipeline verifies its own configuration exhaustively and does not verify the
specifications that describe what it is for.

## What Changes

**One change, in that order: settle the record, then close the gate.** A gate
that fails on arrival gets disabled rather than fixed.

### 1. Every red archived record is settled, each in the form its own defect calls for

- **A task not performed stops being a task, and says why.** `add-prod-data-volume`
  3.4 and 3.6, and `fix-cadvisor-containerd-snapshotter` 2.3, move out of the
  checkbox list into a `## Not performed` section of the same `tasks.md`,
  carrying every word of their existing disposition. Ticking `[x]` for work that
  was not done would make the checkbox lie in the other direction; deleting the
  reason would destroy the record. Neither is acceptable, and a list of
  outstanding work is the wrong container for work that was not done.

  The section covers work not performed **for any reason** — declined on
  judgment, unreachable in the authoring environment, or never captured and no
  longer recoverable. All three occur among these four records, and an author
  facing a case the disclosure does not authorize will tick the box or invent a
  disposition.

  **The disclosure is machine-checked, or it is a bypass.** An unguarded prose
  escape from a gate can be satisfied by relabelling an inconvenient task and
  saying nothing — less information than the unticked box carried, reached
  through the mechanism this change introduces. So `.github/tests` asserts that
  every such entry carries a `Reason:` label with non-empty text, and an entry
  without one fails exactly as an unticked task does.

  The guard reaches **silence, not sufficiency**: a check can find a missing
  label and cannot find a missing thought, so a thin reason passes and review is
  the remedy for it. It also cannot see a task **deleted** rather than disclosed
  — no static check can — which is why the accompanying `AGENTS.md` rule says an
  archived record may be corrected only to say what actually happened, and why
  the pipeline asserts that that rule is still written there.

- **Work that is still wanted becomes a queue entry, not a tick and not prose.**
  `add-prod-data-volume` 3.5 says *"Still open; consider doing this as a
  follow-up plan-only check"* — the `volume_enabled && server_enabled` coupling
  has never been exercised against live state. That is real outstanding work and
  it is recorded in `docs/change-queue.md`, where an archived change cannot bury
  it.

- **`reclaim-superseded-app-images` 4.1–4.3 are ticked with the evidence that
  settles them**, each tick naming the artefact that settles that specific task —
  the host reading, the tag count, the deployed script — and marked as
  retroactive. 4.5 — the reclamation step's reported counts and the first
  steady-state deploy's elapsed time — was not captured and is not recoverable;
  it moves to `## Not performed`. **4.4 is not ticked here.** It is that change's
  `ship:confirm` observation, `AGENTS.md` forbids an agent confirming its own
  gate, and neither waiver class fits an observation that was made and whose
  effect is present. The retroactive reading is put to the operator; their
  confirmation is what closes it, and its absence blocks this change rather than
  being routed around.

- **`refresh-readme-accuracy` 8.6 is removed from `tasks.md`** and recorded in
  prose as performed on 2026-09-08. A general rule follows it into `AGENTS.md`'s
  project-conventions section: **`tasks.md` ends at the archive commit.** Branch
  and working-tree removal happen after that commit is written and cannot be
  recorded in it.

### 2. `openspec validate` becomes a required pull-request check

A new unconditional step in `pr-validation.yml`'s `validate` job runs
`openspec validate --all` and `openspec validate --archived`, from an exactly
pinned manifest — `.github/package.json` plus its lockfile, installed with a
lockfile-exact install, on a pinned Node. `.github/dependabot.yml` gains the
matching `npm` stanza, so the new pin is watched from the day it lands rather
than joining the four manifests queue entry 36 exists to complain about.

The step is unconditional and so is its enclosing job: a step that cannot be
skipped inside a job that can is skippable. **And neither may suppress the
validating command's failure** — the same reasoning read at the same two levels.
Every other property here is satisfied by a step that runs, is pinned, is never
skipped, and throws its result away; that step reports green forever and is
exactly the thing this change exists to remove.

Suppression is excluded by **shape, not by blocklist**. A list of forbidden
constructions is complete until someone writes one nobody listed, and each entry
gets added after the gap it closes has been used. So the step's script is the
validating invocations and nothing else — no shell operator, no override, no
continue-on-error at either level — and the check asserts that shape. It is the
pattern this repository already uses for the test suite's own spawn allowlist and
for the Molecule tier's image digests. The cost is accepted rather than
discovered: a later edit to that step fails the check until the assertion is
updated, which for a step whose purpose is to be un-bypassable is the point.

`.github/tests/test_ci_configuration.py` gains assertions that the step and its
job exist and carry no condition, that it installs from the pinned manifest, that
the step holds its closed form and that neither it nor its job can suppress the
validating command's failure, that the `npm` stanza covers it, that
every `## Not performed` disclosure carries a `Reason:` label, and that the
correction rule above is still stated in `AGENTS.md` — the same division of
labour every other check in this pipeline uses: the workflow does the work, the
suite asserts statically that the workflow says what it should.

The check does **not** go inside `.github/tests` itself. That suite is required
by `openspec/specs/iac-cicd-pipeline/spec.md` to depend only on its runtime's
standard library and on exactly pinned dependencies, and asserts against its own
source that it spawns nothing but `bash` and `sh`. `design.md` records why the
two alternatives that would fit there were rejected.

## Impact

- **Affected specs:** `iac-cicd-pipeline` — one new requirement, and its
  `## Purpose` paragraph, which enumerates the capability's tiers and is not
  itself a requirement, so no delta reaches it; it is updated at archive time.
  *Automated Dependency Updates* lives in `iac-safety-hardening` and is
  **unchanged**: it names `terraform` and `github-actions` as a floor, so an
  `npm` ecosystem violates nothing there, and the obligation to add one comes
  from the new requirement rather than from it.
- **Affected code:** `.github/workflows/pr-validation.yml`,
  `.github/dependabot.yml`, `.github/package.json` (new), its lockfile (new),
  `.github/tests/test_ci_configuration.py`.
- **Affected records:** the `tasks.md` of every archived change
  `openspec validate --archived` names at implementation time — four as of
  2026-09-08 — edited in place under `openspec/changes/archive/`;
  `docs/change-queue.md`; `AGENTS.md`'s project-conventions section.
- **Delivered in three pull requests**, per `design.md` Decision 2: the archived
  records settled, then the gate wired, then the specification record. Correcting
  history and changing the pipeline are different acts and get separate review. A
  record that goes red mid-flight — another change archiving in the meantime —
  takes a pull request of its own rather than riding in with the gate.
- **Not in scope:** performing `add-prod-data-volume` 3.5's live coupling plan
  (queued), and running `openspec validate` from `pre-commit` (see `design.md`).
