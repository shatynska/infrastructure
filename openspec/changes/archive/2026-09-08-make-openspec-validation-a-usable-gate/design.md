## Context

Two halves, and the order between them is the whole design: settle the archived records that `openspec validate --archived` reports red, then make that command a gate. Wiring a check in while it is red produces a check that gets disabled rather than fixed, which is worse than no check because it also spends the reviewer's attention.

The constraints that actually bind:

- `openspec validate --archived` reads one property only — that every `- [ ]` in an archived change's `tasks.md` is `- [x]`. It has no vocabulary for *not done, and here is why*.
- `openspec/specs/iac-cicd-pipeline/spec.md`, *The Continuous-Integration Configuration Is Itself Verified*, binds `.github/tests` to its runtime's standard library plus exactly pinned dependencies, and forbids it a network call, a credential, a container runtime or a Terraform binary. The suite enforces the spawn half against its own AST (`test_the_suite_spawns_no_terraform_binary_or_container_runtime`, `SPAWNABLE = {"bash", "sh"}`).
- `openspec` is an npm binary. This repository has no JavaScript, no `package.json`, and no npm entry in `.github/dependabot.yml`.
- `AGENTS.md` forbids an agent confirming its own `ship:confirm` gate, and requires a waiver to be recorded in the change's own artifacts and granted by the operator.

## Goals / Non-Goals

**Goals.** `openspec validate --all` and `openspec validate --archived` both green, and both run on every pull request as part of the required status check. Every archived record that `--archived` names at implementation time says truthfully what happened — four as of 2026-09-08, and the count has already moved once. The rule that produced the fourth is written down so it stops producing more.

**Non-Goals.** Performing `add-prod-data-volume` 3.5's live coupling plan — it needs a Hetzner token and a plan review, is a change of its own, and is queued. Running `openspec validate` from `pre-commit` (Decision 6). Reforming how `tasks.md` is written in general; only the one rule this change's evidence actually supports is added.

## Decisions

### Decision 1 — A task not performed stops being a checkbox, and the disclosure is checked

`tasks.md` gains a `## Not performed` section. Each entry moves there verbatim, keeping its full existing disposition, and loses its `- [ ]` marker.

**The section covers work not performed for any reason**, not only work declined on judgment. Three of the entries this change moves were declined; one — `reclaim-superseded-app-images` 4.5 — was simply never captured and is no longer recoverable. Authorizing only the deliberate case would leave the second with no honest disposition on the day the gate lands, and an author with no authorized option ticks the box or invents one. What the disclosure must carry is a reason, not a particular *kind* of reason.

**And the disclosure is machine-checked.** This is the correction that matters most in this design, because without it Decision 1 installs its own bypass: a gate whose escape hatch is unguarded prose can be satisfied by relabelling an inconvenient task and saying nothing, which is less information than the unticked box carried. That is precisely the *"guaranteed only until someone does not notice"* posture that *The Continuous-Integration Configuration Is Itself Verified* exists to refuse, and it is the same shape as the `bash -c` evasion Decision 5 declines. Refusing an evasion in one decision and building one in another would not survive contact.

So `.github/tests` asserts statically that every entry under a `## Not performed` heading — in any `tasks.md` under the changes directory, archived or active — carries a `Reason:` label with non-empty text. The scope covers active changes because this change creates such a disclosure in its own `tasks.md` at 12.3, before it is archived; a check that only ever looked at the archive would not see the first disclosure the repository writes. That is a static read of committed files, needs no new dependency, spawns nothing, and is squarely inside that suite's charter — it does not disturb Decision 5, which is about where the *tool* runs, not about what the suite may read. The `Reason:` label is deliberate: a check can find a missing label, and cannot find a missing thought.

**What the guard does and does not reach**, stated so nobody has to discover it:

- It makes **silence impossible** and puts every reason in a reviewable diff. That is the whole of its ambition.
- It **cannot judge the reason's content.** A one-word reason passes. The remedy for a bad reason is review, which is an appropriate remedy for a bad reason and an inappropriate one for no reason at all — that asymmetry is the point.
- It **cannot see a deleted line.** Removing a task outright is invisible to both `openspec validate --archived` and to any check over `## Not performed` entries, and it is the cheaper bypass of the two. This change performs exactly one such deletion itself, at `refresh-readme-accuracy` 8.6, which is why the guard against it is not a check at all but the correction rule Decision 2 puts into `AGENTS.md`: an archived record may be corrected only to say what actually happened. A static check cannot distinguish a task deleted because it should never have been written from one deleted because it was inconvenient. A rule and a reviewer can.

Considered and rejected:

- **A ticked box carrying a "Not performed" note.** Green, cheap, and a lie in the direction that matters most. A ticked box in this repository means the work was done; making it also mean the opposite destroys the only signal the checkbox carries. `openspec validate --archived` would pass while telling the reader something false, which is the exact defect this change exists to close, inverted.
- **Deleting the line.** The reasons on these lines are the most valuable prose in the file — *"no `HCLOUD_TOKEN` in the authoring sandbox"*, *"`modules/volume` was never `terraform validate`'d or `tflint`'d by CI"*. The second is a standing gap in the pipeline, recorded nowhere else.
- **Leaving them unticked and teaching the gate to accept a third marker.** This needs a fork of, or an upstream change to, `openspec`. The point of adopting a tool is not to fork it on first contact.

The section heading is prose, not a task list, so a list of outstanding work contains only outstanding work. That is what the checkbox is for.

### Decision 2 — Editing an archived `tasks.md` is a correction, not a rewrite

Archived changes are the historical record and are not ordinarily touched. This change touches every record `openspec validate --archived` names at implementation time — four as of 2026-09-08 — and the justification has to be explicit or it becomes licence.

Each edit makes the file say what actually happened, using evidence that existed when the change shipped or that is cited to where it lives now. None changes what a change decided, what it built, or what its specification deltas said. The dispositions already written on those lines are preserved word for word.

**The archived edits land in their own pull request, before the one that wires the gate.** Correcting the historical record and changing the pipeline are different acts and deserve separate review; a reviewer reading the workflow diff should not have to also adjudicate four retroactive ticks. `AGENTS.md` sets two pull requests as a floor, not a ceiling, and this change takes three: settle, gate, record. It also leaves the trunk in a defensible state between the first two — the record green, the gate not yet installed — rather than in one where both are half-done.

The temptation to argue the opposite is that `openspec validate --archived` exists and is documented in its own `--help` as *"for pre-commit linting"*, which might be read as presupposing archived records are editable. That reading is weak and this design does not rest on it: the flag's natural use is to fail the pull request that *archives* a red change, which is this change's own delta Scenario 2. The justification above — correction with cited evidence, nothing decided or built changed, dispositions preserved word for word — stands without it.

Because Decision 2 lives in an artifact that becomes archived prose, the rule it states is written into `AGENTS.md`'s project-conventions section alongside Decision 4's, where the next agent will actually meet it.

### Decision 3 — Retroactive ticks carry their evidence, and the ship gate is the operator's

`reclaim-superseded-app-images` 4.1–4.3 are ticked, and each tick names where its evidence lives: the 2026-09-08 reading of `main-server` (`10 images / 3.553 GB / 0 B reclaimable`, one `commerce-ops` tag, `/usr/local/bin/app-deploy` present with its `reclaim()` function), and `prune-unreferenced-host-images-periodically`'s `design.md`, which independently records *"one `ghcr.io/fuperia-it/commerce-ops` image today against 190 before it"*.

A tick with no cited evidence would reproduce the ambiguity being removed. A tick that merely asserts is what an unticked box at least does not do.

4.4 is that change's `ship:confirm` observation, so it is **not** ticked on this session's reading. The reading is put to the operator and their confirmation closes it, per `AGENTS.md`. This is a retroactive confirmation of a gate that should have been closed on 2026-09-07; the record says so plainly rather than presenting it as contemporaneous.

**A waiver is not available here, and offering one would be a worse record than the unticked box.** `AGENTS.md` waives only two classes: an observation that cannot be made, and a change that was the wrong change. Neither fits — the observation *was* made, and its effect is present, not absent. So there are exactly two honest outcomes: the operator confirms the retroactive reading, or 4.4 stays unticked. If the operator does not respond, this change is `blocked:operator-confirmation` and does not proceed past task 6.1. That is the correct behaviour for a ship gate and is stated rather than worked around.

4.5 — the reclamation counts and the first steady-state deploy's elapsed time — was never captured, and the run it describes is gone. It is not recoverable and goes to `## Not performed` under Decision 1.

### Decision 4 — `tasks.md` ends at the archive commit

Branch and working-tree removal is the last act of `ship`, and it happens after the record's own pull request merges — which is after the commit that writes `tasks.md`. A task for it can therefore never be ticked in the file that contains it. `refresh-readme-accuracy` 8.6 is the only instance, and it is the only reason that change is red.

The rule goes in `AGENTS.md`'s **project conventions** section, not in the managed workflow block above it, which is generated and not this change's to edit.

The narrow form is deliberate. The tempting general rule — *"tasks.md must not contain post-archive steps"* — is broader than the evidence: one change in twenty-nine did this, and the surrounding practice of putting the archive step itself in `tasks.md` is fine and should not be disturbed.

### Decision 5 — The gate is a step in `pr-validation.yml`, not a member of `.github/tests`

Four placements were considered.

| Placement | Verdict |
|---|---|
| Step in `pr-validation.yml`'s `validate` job | **Chosen** |
| Python reimplementation inside `.github/tests` | Rejected — reaches one property of three, and drifts |
| A subprocess call to `openspec` from `.github/tests` | Rejected — breaks the suite's own specification |
| A `pre-commit` hook | Rejected — see Decision 6 |

**Why not a Python reimplementation.** Parsing archived `tasks.md` for unticked boxes is thirty lines of standard library, needs no new dependency, and sits squarely inside the suite's charter — the property is a static read of committed files. It was the closest call here. It is rejected because it reaches only one of the three properties the queue entry names: it cannot tell whether the specifications parse or whether a change's deltas are well-formed, and those need `openspec`'s own parser. A reimplementation would also encode this version's notion of a completed task and then silently disagree with the tool the moment either moved.

**Why not a subprocess call from the suite.** It breaks two things the suite asserts about itself: that it spawns nothing outside `bash` and `sh`, and that it depends only on stdlib and exactly pinned dependencies. There is an evasion — a subprocess whose argv head is `bash` and whose command string invokes `openspec` passes the AST check — and it is named here so that it is on the record as refused rather than merely unmentioned. Defeating a check by knowing its shape is the failure mode this whole repository is built against.

The chosen placement needs no amendment to that requirement, because a new step in the workflow is not the suite.

**The division of labour is the pipeline's existing one.** The workflow runs the tool; `.github/tests` asserts statically that the workflow does so, unconditionally, from the pinned manifest. That is exactly how `terraform test`, `gitleaks`, the Molecule tier and the destroy-policy gate are each covered.

The step is unconditional, not path-filtered on the specification directory. Archived records rot with the passage of the trunk, not with the diff of the pull request in front of you — and a pull request that changes no specification file is precisely the one that would carry a stale red past a filter.

Both invocations run: `--all` covers active changes and specs, `--archived` is a separate flag and is not implied by it.

### Decision 6 — Not a `pre-commit` hook

`pre-commit` runs on developer machines. A `local` hook invoking `openspec` fails loudly on a machine without it, or is configured to skip and then reports success — which is the *"verification that cannot reach what it needs skips and reports success rather than failing"* hazard `AGENTS.md` names, installed on purpose. `pr-validation.yml` runs on a runner whose toolchain this repository controls, so "the check ran" and "the check passed" stay distinguishable there.

This is not permanent. If the pin acquires a home that a fresh clone provisions automatically, a hook becomes cheap; that is a later change, not this one.

### Decision 7 — The pin gets a real manifest, and Dependabot watches it

A bare global install pinned inline in a workflow step is an exact pin, and Dependabot cannot see it: its `npm` ecosystem reads `package.json`. This repository already has four exactly pinned manifests that nothing watches — `docs/change-queue.md` entry 36 exists to complain about them. Adding a fifth in the same commit that argues for closing a verification gap would be indefensible.

So: `.github/package.json` pinning `openspec` exactly, its lockfile committed beside it, a clean lockfile-exact install in the workflow step, and an `npm` stanza in `.github/dependabot.yml` naming that directory.

A lockfile-exact install rather than a resolving one: it installs the lockfile exactly and fails if the manifest and the lockfile disagree, which is the same property `terraform init` gets from a committed `.terraform.lock.hcl`.

**The runtime is pinned too.** A freshly resolved Node beneath an exactly pinned `openspec` leaves the pin describing less than it appears to — the same defect the Molecule tier's image-digest rule exists to close, where a pinned toolchain ran against an unpinned image. The Node major version is named explicitly, and the setup action is pinned like every other action here.

Cost, stated plainly: a JavaScript manifest pair in a repository with no JavaScript. That is the honest price of running the tool rather than reimplementing it, and Decision 5 records what reimplementing it would cost instead.

`test_dependabot_configures_both_required_ecosystems` asserts membership rather than an exact set, so adding a third ecosystem does not break it.

### Decision 8 — This change's own confirm gate is the positive observation; the negative demonstration is separate

The gate's effect has two observable halves, and they are not equally available.

- **The positive.** On the merged pull request, the step ran, reported and passed — and it ran on a pull request touching no Terraform file, which is what distinguishes "the check is present" from "the check is not skipped". This is performable by reading the run, needs nobody's cooperation, and is a genuine observation of the change's effect. **It closes `ship:confirm`.**
- **The negative.** A throwaway pull request that unticks one archived task, confirmed red, then closed. What the red proves is the *composition* — that a non-zero exit from the tool becomes a failed required check — since its two halves are separately held: the exit status is this change's observed premise, and non-suppression is asserted statically per Decision 9.

An earlier draft made both halves one task and forbade waiving it. That was wrong in a way worth recording, because it is the failure this change is about. If the operator declined the throwaway experiment, the task could not be ticked and could not be waived, so the change would archive with an outstanding task — red under the gate it had just installed — and the tempting escape was to disclose it under `## Not performed`. But `AGENTS.md` closes `ship:confirm` by observation or by a classed, operator-granted waiver, and a disclosure is neither. Decision 3 refuses exactly that leniency to `reclaim-superseded-app-images` 4.4. Granting it to this change and withholding it from another change's record is the asymmetry the whole proposal argues against, and it would have left the strongest possible precedent for treating `## Not performed` as an escape hatch — inside the change that built it.

Splitting the two removes the problem rather than routing around it. The positive half closes the gate honestly. The negative half becomes a whole task that either happens or does not, and a whole task not performed is precisely what Decision 1's disclosure is for — with a stated reason, and with a queue entry carrying it forward.

**What makes that disclosure safe rather than a hole** is Decision 9. An earlier draft of this decision described the negative demonstration as the only reachable evidence that the thing gates, which would have made disclosing it a real loss — the change's central claim resting on an experiment the operator can decline. That was wrong, and wrong in the same direction as the fallback it justified: it treated an unreachable *composition* as an unreachable *property*. With non-suppression asserted statically, what 12.3 adds is the confirmation that GitHub reports a failed step as a failed check. That is worth observing and not worth blocking on.

### Decision 9 — The step's failure is asserted statically, not demonstrated

Every other obligation this change places on the new step — it exists, it is unconditional, its job is unconditional, it installs from the pinned manifest on a pinned runtime — is satisfied by a step that does all of that and then throws its result away. `continue-on-error: true`, a trailing `|| true`, a `set +e`: any of them produces a step that runs on every pull request, is exactly pinned, is never skipped, and reports green forever.

That would be this change installing the precise thing it was written to remove: a check nobody can see failing. It is worth saying plainly that the plan carried this hole through three review rounds while arguing against it in prose — the failure mode is not that people do not know better, it is that the properties that are easy to state are not the property that matters.

So `.github/tests` asserts that neither the step nor its enclosing job suppresses the validating command's failure, and the delta says so as an obligation in its own right rather than leaving it implied by *"the required status check SHALL fail"*.

**At both levels, for the reason the change already learned once.** Decision 5 established that a step which cannot be skipped inside a job which can is skippable. The first draft of this decision then scoped suppression to the step alone — so a single `continue-on-error: true` on the `validate` job would have satisfied every word of it. The same asymmetry, one paragraph later, in the paragraph written to close asymmetries.

**A closed shape, not a blocklist.** The first draft also forbade "a trailing disjunction, disabling exit-on-error, or any other means", and then required that open-ended negative be asserted statically — which cannot be done. `|| :`, `; true`, `if ! …; then`, a pipe that loses `pipefail`, a `shell:` override, the step relocated into a composite action: a blocklist is complete only until someone writes the entry nobody thought of, and every entry gets added after the gap it closes has been used. So the delta specifies the step's shape positively and completely — the validating invocations and nothing else, no shell operator, no override, no continue-on-error at either level — and the check asserts *that*.

This is the pattern already in use here twice. `SPAWNABLE = {"bash", "sh"}` is an allowlist, not a list of forbidden binaries. The Molecule tier requires an immutable digest rather than forbidding the mutable tags it has met so far. Both are checks that stay correct against constructions their authors never saw.

**The cost, accepted rather than discovered.** A closed shape means any legitimate future edit to that step's script fails the check until the assertion is updated. For a step whose whole purpose is to be un-bypassable, an edit that must be noticed is the point.

**Static rather than demonstrated**, deliberately. A demonstration establishes it on the day it was run; an assertion establishes it for every later edit of the workflow, including the edit six months from now that adds `continue-on-error: true` to quiet a flaky run. This is the same reasoning the Molecule tier uses for its image digests: the property is about what the committed file says, so it is checked where committed files are checked.

### Decision 10 — The gate rejects two states this workflow prescribes, and the fix is a written rule

Found by code review of the gate, not by the plan. `openspec validate --all` fails a change directory carrying no specification deltas:

```
✗ change/zz-probe-handoff
  ✗ [ERROR] Change must have at least one delta. No deltas found.
```

`AGENTS.md` prescribes exactly that state. *"Opening"* a change means a branch of its own and a `handoff.md`, **with no proposal** — so the moment such a branch carries a pull request, the unconditional, un-suppressible gate this change installs refuses it. The same applies mid-`plan:drafting`, where a proposal exists and deltas do not yet.

This is the gate colliding with the workflow that asked for it, and neither `proposal.md` nor the delta anticipated it.

**The mitigation already exists and is already used here.** `skip_specs: true` in the change's `.openspec.yaml` declares zero deltas acceptable; four archived changes use it. Verified on a copy of `openspec/`: with `schema:`, `created:` and `skip_specs: true`, a handoff-only directory passes — with or without a proposal beside it.

One trap worth recording, because the first probe hit it: `skip_specs: true` **alone** in the file does not work. Dropping `schema:` makes the change fail to resolve, and the error is the identical "must have at least one delta" message — so the setting reads as ineffective when the real fault is the missing key. An author debugging that would reasonably conclude the escape does not exist.

So the rule goes into `AGENTS.md`'s project conventions: an opened change gets that file at the moment it is opened, and the `skip_specs` line is dropped when its deltas are written.

**Considered and rejected: exempting delta-less changes in the check itself.** The gate would then pass a change that *should* have deltas and has none, which is a real defect — a specification-driven workflow whose specification step was skipped. `skip_specs` is a per-change declaration a human writes and a reviewer sees in the diff; an exemption computed by the checker is invisible. The declaration is the better mechanism, and it already exists.

## Risks / Trade-offs

- **One stale archived record blocks every pull request in the repository.** This is the direct cost of the unconditionality argued for in Decision 5, and it is the change's largest operational consequence: a red `--archived` is not scoped to the pull request that caused it, so an unrelated and urgent change is blocked until the record is settled. That is the gate working as designed — a record nobody is obliged to fix is the state this change exists to end — but the operator should meet it here rather than at 2am. The remedy is always to settle the record (a tick with evidence, or a disclosure with a reason), never to disable the step.
- **`openspec` is a young tool and `--archived` may change meaning across versions.** Mitigated by the exact pin and by Dependabot surfacing each bump as a reviewable pull request rather than as a silent resolution.
- **A future archived change that is legitimately incomplete now fails CI.** That is the gate working. The escape is Decision 1's `## Not performed` section, which is a disclosure, not a suppression — it costs a sentence saying what was not done and why.
- **The evidence for the retroactive ticks is a host reading taken today, not a contemporaneous record.** Stated as such on the tasks themselves. It is strictly better than the unticked box, and it is corroborated by a second, independently written source in the repository.
- **Editing archived records could become a habit.** The guard is the correction rule task 5.2 writes into `AGENTS.md` — an archived record may be corrected only to say what actually happened, with evidence cited. Decision 2 is the reasoning behind that rule, and reasoning alone would not survive this change's own archiving, which is why the rule leaves the artifact and goes into the conventions file.

## Where each delta scenario is verified

This project has three test commands. Two of this delta's scenarios look as though they reach none of them; both in fact decompose into a part that is statically checkable and a part already observed, leaving only their composition for the confirm gate. Saying so here is cheaper than the test author discovering it.

| Scenario | Home |
|---|---|
| Malformed specification or delta fails the pull request | **Decomposed** — see below. The tool's non-zero exit is this change's observed premise; non-suppression is asserted in `.github/tests/*.py`; the composition is observed at `tasks.md` 12.3 |
| Archived change with outstanding tasks fails the pull request | **Decomposed**, same way |
| The check cannot report success over a failed validation | `.github/tests/*.py` — asserts the step holds the closed form the delta specifies, and that neither it nor its enclosing job declares continue-on-error in any form. **Not** a blocklist of evasions; see Decision 9 |
| Unperformed work disclosed without a reason fails the check | `.github/tests/*.py` — a static read of committed files |
| Validation runs regardless of what the pull request touched | `.github/tests/*.py` — asserts the step and its job carry no condition |
| Tool not resolved freshly at run time | `.github/tests/*.py` — asserts the step installs from the manifest on a pinned runtime |
| Pin watched by the dependency-update configuration | `.github/tests/*.py` — asserts the `npm` stanza names the manifest's directory |

The first two scenarios look unreachable and are not. Each is a composition of two facts that are separately established:

1. **`openspec validate` exits non-zero on a bad record.** This is not an assumption — it is the observed premise of the whole change; the command exits 1 on this repository today, which is why there is a change at all.
2. **The step does not discard that exit status.** A static read of committed YAML, asserted in `.github/tests`, and the one property every other obligation in the delta is silent about.

What remains unautomated is only the composition — that GitHub reports a failed step as a failed check — and `tasks.md` 12.3 observes it. Treating the composite as atomic and unreachable is what made 12.3 look load-bearing enough to block on; it is not, once its two halves are separately held. Only 12.2 closes `ship:confirm` — see Decision 8.

## Migration Plan

Settle the records first and confirm `openspec validate --archived` is green, then wire the gate — in a second pull request, per Decision 2. The gate lands green or it does not land.

## Resolved questions

- **The retroactive `ship:confirm` reading for `reclaim-superseded-app-images` 4.4 — confirmed by the operator on 2026-09-08.** The observation that change's own text asks for is *the single tag that deploy superseded is gone and the tag it deployed remains*; `main-server` shows one `ghcr.io/fuperia-it/commerce-ops` against the 190 that change recorded. The reading was put to the operator because `AGENTS.md` forbids an agent closing its own gate, and because neither waiver class fits an observation that was made and whose effect is present.

  This is a **retroactive** confirmation of a gate that should have closed on 2026-09-07, and task 4.4 records it as such rather than presenting it as contemporaneous. It unblocks task 6.1; without it this change would have sat at `blocked:operator-confirmation`.
