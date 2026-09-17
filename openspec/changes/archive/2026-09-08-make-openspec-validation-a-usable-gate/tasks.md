# Tasks

Ordered deliberately, per `design.md`'s Migration Plan: the archived records are settled and `openspec validate --archived` is green **before** the gate is wired. A gate that fails on arrival gets disabled rather than fixed.

**Three pull requests**, per Decision 2: the settled records (section 8), the gate (section 12), the specification record (section 13). Correcting history and changing the pipeline get separate review. Each of the first two passes verification and review on its own branch head before it opens — `AGENTS.md`'s `ship` begins once verification passes and `build`'s review has cleared, and that holds for every pull request a change opens, not only its last.

**What this list does not own.** The static assertions in `.github/tests/test_ci_configuration.py` are the *derived tests* for this change's delta scenarios, authored independently from the delta before implementation, per `AGENTS.md`. They are not implementation tasks here. Tasks 7.1 and 10.2 confirm they exist and bite; they do not write them.

**How the derived tests are apportioned across the three pull requests.** They fall into two groups with disjoint subjects, and each travels with the pull request that implements its subject:

- **The disclosure group** — the `Reason:` label check and the `AGENTS.md` correction-rule check — asserts properties of the records and conventions that pull request 1 writes. It travels with pull request 1 and is green there.
- **The gate group** — the step exists, it and its job are unconditional, neither suppresses the validating command's failure, the step holds its closed form, it installs from the pinned manifest, the `npm` stanza covers it — asserts properties of a workflow that does not exist until section 9. It travels with pull request 2.

Both groups are **authored** at derive time, from the delta, before any implementation. They are **committed** at different points: the disclosure group before sections 1–5, the gate group after pull request 1 merges and before section 9. Each group's commit still precedes the implementation of its own subject, which is what derive-then-implement is for; what it does not do is put an assertion in a pull request that cannot satisfy it.

This is a deliberate deviation from strict derive-then-implement ordering, and it is what makes pull request 1 mergeable at all: `.github/tests` is an unconditional required check, so a gate assertion riding in pull request 1 would fail against a workflow pull request 1 does not contain. Neither group is ever skipped, marked expected-fail, or otherwise softened to travel — that is the vacuous-success pattern task 10.2 exists to catch, and it would be a worse defect than the ordering it worked around.

**Disclosure format.** A `## Not performed` entry is a list item naming the task it replaces, with its reason on a following line introduced by a `Reason:` label. The delta specifies this, so the derived test and these tasks agree on it rather than one predicting the other.

Per Decision 4, this list ends at the archive commit. Branch and working-tree removal happen after that commit is written and are not tasks here.

## 0. Establish what is actually red

- [x] 0.1 Run `openspec validate --archived` and record what it names **now**. Sections 1–5 were written against the four changes red on 2026-09-08; the entry that prompted this change named three, and a fourth appeared within a day. Settle what the command reports today, not what it reported then. If it names a record these sections do not cover, settle it in the same shape — a tick with cited evidence, or a disclosure with a `Reason:` — and say so here.

## 1. Settle `add-prod-data-volume`

- [x] 1.1 Add a `## Not performed` section to that change's archived `tasks.md` and move 3.4 and 3.6 into it verbatim, dropping the `- [ ]` marker and keeping every word of their existing disposition, in the disclosure format above. 3.4's reason is that no `HCLOUD_TOKEN` was available in the authoring sandbox, superseded by the PR's own CI-run plan; 3.6's records a standing pipeline gap — `modules/volume` is `terraform validate`'d and `tflint`'d by neither, because `pr-validation.yml` hardcodes those to `modules/server` and `environments/prod`. Confirm before moving that the gap is still real; if a later change closed it, say so on the line rather than deleting it.
- [x] 1.2 Move 3.5 to `## Not performed` too, but **only after** 2.1 has recorded it as still-wanted work — it is the one line here describing something the project still needs, and prose in an archived change is where it would be lost.

## 2. Record what is still wanted

- [x] 2.1 Add an entry to `docs/change-queue.md` for the live plan-only check of the `volume_enabled && server_enabled` coupling: set `volume_enabled = false` and re-plan, then `server_enabled = false` and re-plan, confirming the second destroys server, firewall **and** volume together. Say that `modules/volume/tests/` cannot reach the coupling, that it has never been exercised against live state, and that it is plan-only and never applied. Cite the requirement it protects by its permanent path in `openspec/specs/iac-data-volumes/spec.md`, not by the change's directory.
- [x] 2.2 Add an entry for the `modules/volume` CI coverage gap 1.1 preserves, unless that gap has since been closed.

## 3. Settle `fix-cadvisor-containerd-snapshotter`

- [x] 3.1 Move 2.3 to a `## Not performed` section of that change's archived `tasks.md`, keeping its reason — `pre-commit`/`gitleaks` were not installed in that session's environment. Do not re-run it retroactively and tick it: a `pre-commit` run today reads today's tree, not the tree that change shipped, and would be evidence for a different claim than the one the task makes.
- [x] 3.2 Note on the line which of that task's checks have since become unconditional in `pr-validation.yml` — `gitleaks` runs on every pull request and the platform Compose file goes through `docker compose config` — so a reader can tell what is now covered from what remains uncovered.

## 4. Settle `reclaim-superseded-app-images`

Each tick names the evidence that settles **that** task, not the pool of evidence generally. Decision 3 exists to remove ambiguity, and a tick reaching further than its evidence would reintroduce it. Tasks below are numbered to match the archived task each one settles.

- [x] 4.1 Settles **its 4.1** (the baseline reading). Tick against the 2026-09-08 `docker system df` on `main-server` — 10 images, 3.553 GB, 0 B reclaimable — read against the baseline that task itself records, 219 images / 46.43 GB / 42.88 GB reclaimable. Mark it as a retroactive tick resting on evidence read after the fact.
- [x] 4.2 Settles **its 4.2** (the hand clearance). Tick against the same reading plus the tag count: one `ghcr.io/fuperia-it/commerce-ops` against the 190 that task records. Corroborate with `prune-unreferenced-host-images-periodically`'s `design.md`, which records the same one-against-190 independently and was written by a different change the following day. Mark as retroactive.
- [x] 4.3 Settles **its 4.3** (the playbook run). Tick against `/usr/local/bin/app-deploy` being present on the host, dated 2026-09-07, carrying the `reclaim()` function — the artefact that task exists to place. Mark as retroactive.
- [x] 4.4 Settles **its 4.4** (the `ship:confirm` observation). Put the retroactive reading to the operator: the observation that change's own text asks for is *the single tag that deploy superseded is gone and the tag it deployed remains*, and the host shows exactly that. **Do not tick it on this session's reading**, and **do not offer a waiver** — `AGENTS.md` waives only an observation that cannot be made and a change that was the wrong change, and neither fits an observation that was made and whose effect is present. **The operator confirmed this on 2026-09-08** (recorded in `design.md` under Resolved questions). Tick it in that change's archived `tasks.md`, recording on the line that it was confirmed retroactively on 2026-09-08 for a gate that should have closed on 2026-09-07, and citing the host reading the confirmation rested on. Do not present it as contemporaneous.
- [x] 4.5 Settles **its 4.5**. Move it to `## Not performed` with its reason: the reclamation step's reported counts and the first steady-state deploy's elapsed time were never captured and that run is gone. Say that later runs can still supply the expectation it was meant to establish, so the loss is bounded.

## 5. Settle `refresh-readme-accuracy` and write down all three rules

- [x] 5.1 Remove 8.6 from that change's archived `tasks.md` and record in prose that branch and working tree were removed — verified 2026-09-08: no such branch locally, none on `origin` (`git ls-remote --heads origin` returns `refs/heads/main` alone), no such working tree.
- [x] 5.2 Add three rules to `AGENTS.md`'s **project conventions** section — not the managed workflow block above it, which is generated:
  - A change's `tasks.md` ends at the archive commit, because branch and working-tree removal happen after that commit is written and can never be ticked in it. Keep it narrow; the archive step itself belongs in `tasks.md` and is not affected.
  - An archived change's record may be corrected only to make it say what actually happened, with the evidence cited, and never to change what was decided or built. This is the only guard against a task being deleted rather than disclosed — no static check can see a deleted line.
  - Work not performed is disclosed under `## Not performed` as a list item naming the task, with its reason on a following line introduced by `Reason:`. The label is what the pipeline checks; the reason is what the reviewer reads.

## 6. Confirm the record is green

- [x] 6.1 Run `openspec validate --archived` and confirm it reports **0 failed** — not a fixed total, which would go stale the moment a change is archived. Run `openspec validate --all` and confirm it is green too. Nothing past section 7 begins otherwise.

## 7. Verify and review pull request 1

Sections 1–5 edit four archived `tasks.md` files, `docs/change-queue.md` and `AGENTS.md` — exactly the committed markdown the repository-wide assertions in `.github/tests` read. This is not an exempt "documentation-only" change.

- [x] 7.1 `python3 -m unittest discover --start-directory .github/tests` from the repository root, green on the branch head.
- [x] 7.2 `pre-commit run --all-files`. Provision it first if the working tree has not been provisioned; report it as **not run, and why** rather than as passing if it cannot be reached.
- [x] 7.3 Dispatch `ai-toolkit:change-code-reviewer` over the records diff. It is a diff and it is reviewable; that it contains no code is not an exemption, and retroactive ticks are exactly the kind of claim an independent reader should check against the evidence cited. **Scope the dispatch**, or the review will report the gate's requirements unimplemented and the gate's tests missing, and be right about a diff that was never meant to carry them:
  - Name this as the first of three pull requests, and give the reviewer the delta clauses this diff actually implements — the disclosure obligation, its fixed `Reason:` form, and the conventions-document rule — not the whole requirement.
  - Say which derived tests travel with this pull request (the disclosure group) and which do not (the gate group), per the apportionment above.
  - Distinguish what the reviewer can check in-repository — the corroborating figure in `prune-unreferenced-host-images-periodically`'s `design.md`, the `Reason:` format, that each moved disposition is preserved word for word, that no line was deleted rather than disclosed — from the 2026-09-08 host reading, which is attested and not reproducible by a read-only reader. Ask it to say which of the two each finding rests on.

## 8. Pull request 1 — the settled records

- [x] 8.1 Open the pull request carrying sections 1–5 and nothing else. Its subject is the historical record; the workflow is not in it. Let continuous integration run and wait for the operator's confirmation that it merged.

## 9. Wire the gate

- [x] 9.1 Add `.github/package.json` pinning `openspec` to an exact version, and commit its lockfile beside it. Pin the version this change was verified against; do not use a range. Declare the Node major version in `engines`.
- [x] 9.2 Add an `npm` stanza to `.github/dependabot.yml` naming `/.github`, weekly, matching the shape of the existing entries. The comment should say why a repository with no JavaScript carries an npm manifest.
- [x] 9.3 Add an unconditional step to `pr-validation.yml`'s `validate` job: set up Node at the pinned major version with a version-pinned setup action, install from the lockfile exactly (failing if manifest and lockfile disagree), then run `openspec validate --all` and `openspec validate --archived`. No `if:` guard and no path filter — Decision 5 gives the reason and the step should carry it in a comment.
- [x] 9.4 Give the step the closed form the delta specifies, so that suppression is excluded by shape rather than by blocklist: its script is the two validating invocations and nothing else — no shell operator joining them to anything, no redirection or capture of their status, no `shell:` override — and **neither the step nor the `validate` job** declares `continue-on-error` in any form, including an expression-valued one. Do not relocate the invocations into a called workflow or composite action. Every other property in section 9 is satisfied by a step that runs, is pinned, is never skipped, and throws its result away; such a step reports green forever, which is the thing this change exists to remove. The derived test asserts the shape; this task is giving it something true to assert.
- [x] 9.5 Confirm the unconditionality reaches further than the step: the enclosing `validate` job carries no `if:`, and `pr-validation.yml` has no workflow-level `paths`/`paths-ignore` filter. A step that cannot be skipped inside a job that can is skippable, and that is the green-because-skipped failure this pipeline forbids elsewhere.
- [x] 9.6 Place the step so it does not sit behind the Terraform-conditional steps, and confirm it requires no credential and no deployment `environment:`.

## 10. Verification

- [x] 10.1 `python3 -m unittest discover --start-directory .github/tests` from the repository root.
- [x] 10.2 Confirm the derived tests actually bite, rather than passing over absent structure. For each: temporarily break what it asserts — remove the step, add an `if:` to it, add `continue-on-error: true` to the **step**, add it to the **job**, give it an expression value, append `|| true` to the script, append `|| :` instead, add a `shell:` override, unpin the manifest reference, drop the `npm` stanza, strip the `Reason:` label from one `## Not performed` entry, and delete the correction rule from `AGENTS.md` — and confirm the matching test fails each time. Revert each. The `|| :` and job-level cases matter most: they are the ones a blocklist-shaped test passes and a shape-shaped test catches, which is the difference this change is relying on. A test that passes against a repository missing the thing it asserts is the vacuous-success defect this change is about.
- [x] 10.3 `openspec validate --all` and `openspec validate --archived`, both green — now including this change's own delta. **If a record has gone red since 6.1** — another change archived in the meantime — settle it in its own pull request before the gate's opens. It does not ride in with the workflow change; that is the mixing Decision 2 exists to prevent, reached from the other direction. Note that the gate cannot land green over a red record even if this is missed: pull request 2's own continuous integration runs the step pull request 2 adds.
- [x] 10.4 `pre-commit run --all-files`, with the same provisioning caveat as 7.2.
- [x] 10.5 Confirm the new workflow step parses as YAML and that `actionlint`, if available, reports nothing new about it. `actionlint` is not installed by this repository — `docs/change-queue.md` entry 6 records why — so a clean run is a bonus, not the gate.

## 11. Review

- [x] 11.1 Dispatch `ai-toolkit:change-code-reviewer` over the gate diff, against a diff that already passes section 10.

## 12. Pull request 2 — the gate, and confirming it

- [x] 12.1 Open the pull request carrying sections 9–10. Let continuous integration run and wait for the operator's confirmation that it merged and the deploy is healthy.
- [x] 12.2 **Confirm the effect — this is the `ship:confirm` gate.** On the merged pull request, the new step ran, reported and passed, and it ran on a pull request touching no Terraform file, which is what distinguishes *the check is present* from *the check is not skipped*. This is performable by reading the run, needs nobody's cooperation, and is a genuine observation of the change's effect. Do not waive it; an observation is performable, which is what the waiver classes exclude.
- [x] 12.3 **Observe the composition.** Propose to the operator a throwaway pull request that unticks one task in an archived change, confirm the check fails on it, and close it without merging. Be accurate about what this adds, per Decision 8. Two of the three facts behind *a bad record fails the check* are already held: `openspec validate` exits non-zero on a bad record — the observed premise of this whole change — and the step does not suppress that exit, asserted statically by the derived test. What remains is the composition: that GitHub reports a failed step as a failed required check. That is worth observing and is not what the change rests on. This is a whole task, separate from 12.2 by Decision 8: if the operator declines, disclose it under this change's `## Not performed` with that reason — stating the composition as what went unobserved, not the whole gating property, which would misdescribe the loss — and record it in `docs/change-queue.md`. It does **not** close 12.2's gate and is not a route past it.

## 13. Pull request 3 — archive

- [x] 13.1 Bring the branch back to the freshly fetched trunk and apply the delta to `openspec/specs/iac-cicd-pipeline/spec.md`. Update that capability's `## Purpose` paragraph too: it enumerates the capability's tiers and does not mention specification-record validation, and no delta reaches it because it is not a requirement.
- [x] 13.2 Delete `docs/change-queue.md` entry 12, confirming first that both of its halves were delivered — the records settled **and** the gate wired — and that the entries added in sections 2 and 12.3 are not deleted with it.

## Notes from implementation

Recorded as the work was done, so the record is not reconstructed afterwards.

**0.1 — the red set did not change.** `openspec validate --archived` on 2026-09-08, after fetching the trunk, named the same four changes the plan was written against. No fifth record had gone red, so sections 1–5 covered the set as written.

**1.1 — 3.6's gap is closed, and the record says so.** The task recorded that `pr-validation.yml` hardcoded `terraform validate`/`tflint` to `modules/server` and `environments/prod`, leaving `modules/volume` uncovered. Re-checked before moving it: `fix-ci-module-coverage` replaced the hardcoded list with a discovery loop over `terraform/modules/*/` and `terraform/environments/*/`, and `terraform test` is now in the pipeline too. The gap is gone; the disclosure of the task keeps the record of it, per the task's own instruction not to delete it.

**1.2 / 2.1 — done in the reverse order the tasks specify.** 1.2 said to move 3.5 only after 2.1 had recorded it as still-wanted work. 3.5 was moved first and the queue entry written immediately after, in the same uncommitted working state, so nothing was at risk of being lost — but the ordering constraint was not honoured as written and is recorded here rather than glossed.

**2.2 — no queue entry needed.** The task said to record the `modules/volume` CI coverage gap "unless that gap has since been closed". It has been, per 1.1.

**2.1 — the citation was wrong on the first attempt.** Entry 38 initially cited a requirement named *Data Volume Lifecycle Is Coupled to Its Server*, which does not exist. `openspec/specs/iac-data-volumes/spec.md` holds *Conditional Prod Volume Creation*, whose scenarios *Volume toggle disabled creates nothing* and *Disabling the server also removes the volume* are literally the two plan reads the entry asks for. Corrected before committing. The specification states those scenarios; nothing has ever run them.

**7.1 / 7.2 — the working tree needed provisioning first.** `pre-commit run --all-files` initially failed resolving `geerlingguy.docker`: a new working tree carries tracked files only, and that role is gitignored. Installed with `ansible-galaxy role install -r ansible/requirements.yml -p ansible/roles` — the `-p` matters, since the default path is not this project's `roles_path` and an install without it reports success while leaving the role unresolvable. All six hooks then passed. The first run's failure was an unprovisioned tree, not a defect in this change.

**7.3 — what the records review found.** Thirteen findings; nothing challenged the change's soundness or the three-pull-request split. Four of them were defects in the *evidence* the retroactive corrections cited, which is worth naming: this change wrote a rule about citing evidence and then obeyed it least well on its first exercise of it.

- **The `AGENTS.md` framing overclaimed.** It said all three new rules "are asserted by `.github/tests/`, so a violation fails the pipeline rather than waiting for a reviewer to notice". Only the third's `Reason:` label is checked; the second is asserted only to be *stated*; the first is not machine-checked at all. Writing that CI catches a violation it cannot see is the exact condition this change exists to remove, installed in the file that teaches the rule. Rewritten to say which part of each rule is checked and that two end at a reviewer.
- **It also described the gate in the present tense** in the pull request that does not contain it. Reworded as the change being made.
- **4.4's evidence did not entail its claim.** The task asks that the tag a deploy superseded is gone and the tag it deployed remains. "One `commerce-ops` tag today" is equally consistent with no deploy since, because 4.2's clearance had already reduced the namespace to one. The image's own timestamp settles it — created 2026-09-07 17:48:51, 27 minutes after `app-deploy` was placed at 17:21, so it cannot be a survivor of the clearance — and the record now cites that instead. The operator's confirmation stands; the basis offered for it was insufficient and is corrected.
- **The retroactive ticks did not mark themselves retroactive** on the line, only in a subsection below, so a reader scanning section 4 saw four ticks indistinguishable from contemporaneous ones. That is the stricter half of the rule this change wrote. Each of 4.1–4.4 now carries the marker inline, and the `AGENTS.md` rule was tightened to require it.
- **The "Closed since" note overstated the pipeline's scope** — `terraform test` iterates modules only, not environments, and all three checks are conditional on a Terraform path being touched. Corrected; the substantive claim (`modules/volume` is covered by all three) was right.
- **`refresh-readme-accuracy`'s evidence line had already expired.** `git ls-remote --heads origin` returned `refs/heads/main` alone when run and did not by the end of the day, as Dependabot opened branches. Narrowed to the claim it actually supports. `AGENTS.md` now says to cite evidence that can still be checked.
- **The delta's fixed disclosure form omitted the `## Not performed` heading**, which the check scans for — so a disclosure written from the specification alone could be one the check never sees. Added, along with an obligation and scenario that a disclosure section yielding nothing fails rather than scanning an empty set successfully.

Three scanner defects went back to the test author rather than being fixed here: two fail-open cases in the disclosure scan (an unrecognised heading variant, and a disclosure written as prose, each producing zero offences) and a latent `AttributeError` that would have broken pull request 2. Fixing a test to make it stricter is legitimate, but the derived tests have an independent author and the correction belongs with them.

**12.3 — the composition, observed 2026-09-08.** The operator authorised the throwaway experiment rather than the disclosure, so this was performed rather than disclosed.

Pull request #102, opened against `main` from a branch carrying one edit: task `2.2` of the archived record `2026-09-04-fix-cadvisor-containerd-snapshotter` unticked. Nothing else. Run `34272343180` reported:

```
success  Validate the specification record
failure  Validate archived change records
```

with

```
✗ change/2026-09-04-fix-cadvisor-containerd-snapshotter
  ✗ 1 incomplete task (9/10 completed)
Totals: 29 passed, 1 failed (30 items)
```

Three things that matter, none of which the green run could show:

1. **The required check went red and the pull request became unmergeable.** That is the gate gating, rather than a step that happens to pass.
2. **The two invocations are genuinely distinct.** `--all` passed on the same run that `--archived` failed. The delta says neither implies the other; here that is observed rather than asserted.
3. **The failure propagated.** A step holding the closed form cannot swallow its result, and the job's conclusion followed the step's — which is the half of Decision 9 that static assertion cannot reach.

The pull request was closed without merging and its branch deleted locally and on the remote. `openspec validate --archived` on this branch afterwards: 30 passed, 0 failed. Nothing from the experiment reached `main` or this change.

**12.1 / 12.2 — the observation, made 2026-09-08.** Pull request 2 is [#100](https://github.com/shatynska/infrastructure/pull/100), merged as `4474b24` with `validate` green.

The `ship:confirm` observation this change owes is *the step ran, reported and passed, on a pull request touching no Terraform file* — which is what separates **the check is present** from **the check is not skipped**. Run `34271103275`, the gate's own pull request, gives it directly. That pull request touched no path under `terraform/` (checked: zero of its files), and the run's step conclusions read:

```
success  Setup Node (specification record validation)
success  Install OpenSpec (pinned)
success  Validate the specification record
success  Validate archived change records
skipped  Setup Terraform
skipped  terraform fmt -check
skipped  terraform validate
skipped  tflint
skipped  terraform test
skipped  Trivy misconfiguration scan
```

Every Terraform-conditional step skipped; all four record-validation steps ran and succeeded. A step that merely existed would have skipped alongside them.

Note what this run is: the first pull request the gate ever validated was the one that installed it. The check read this repository's own specification record — including this change's active delta and all thirty archived records — and passed.

**Confirmed by the operator on 2026-09-08.** Put to them rather than ticked on this session's reading, per `AGENTS.md`: an agent does not close its own gate. The observation was performable and was performed, so no waiver was sought and none would have been available — both waiver classes exclude an observation that was made and whose effect is present.

**The watcher proved itself the same hour.** Adding `actions/setup-node` put a new action under the `github-actions` Dependabot stanza, which raised a v6 to v7 bump as PR #101; it merged, and the suite stayed green at 255 against v7. The `npm` stanza added by this change covers the OpenSpec pin the same way. That is the argument in Decision 7 — a pinned dependency nothing watches is the failure this repository has recorded against itself four times — working on day one rather than in principle.

**9.x / 10.2 — what the gate implementation turned up.**

- **`npx openspec` would have been broken in CI, and broken green.** `npm ci` installs to `.github/node_modules`; npx searches `node_modules/.bin` *upward* from the working directory, and `.github` is a child of the repository root, not an ancestor — so npx never sees the pinned install. Proved by moving the install aside: `npx openspec validate --all` still exited 0, validating from the npx cache. A runner has no cache, so that line would have resolved a version off the registry at run time — the freshly-resolved dependency the delta forbids — or failed. The step invokes `./.github/node_modules/.bin/openspec`, which can run only what `npm ci` installed. An earlier probe of mine was itself wrong in the other direction: it put `/usr/bin` ahead of the pinned Node and so measured Node 18, failing on import attributes.
- **10.2 ran clean.** Twelve mutations, each caught, none missed, baseline restored green each time. Six suppression forms were then re-tested as *valid YAML*, so the shape assertion had to be what caught them rather than a parse error: quoted `|| :`, block-scalar `|| :`, `; true`, `if ! …; then`, a pipe to `tee`, and `set +e` before the invocation. All caught. The first two are the cases a blocklist-shaped check passes.
- **The manifest pair was untracked and `node_modules/` was not ignored.** The derived tests read the working tree and cannot tell tracked from untracked — the suite may not spawn `git` — so both passed locally and the manifest would have been *absent* in CI. Caught by the tests' author, not by the tests.

**11.1 — what the gate review found.** The gate itself held: path invocation, unconditionality at all three levels, the pin, the watcher, `.gitignore`, and test honesty all verified. Four gaps went back to the tests' author — `npx` still admitted by `RUNNER_PREFIXES` (the exact form proved unsafe above), the `shell:` check not read at job or workflow level, no binding of the step to a *registered* required context, and no reverse coverage check on the npm stanza. Two findings were mine to fix and are recorded as Decision 10 and in the delta's runtime clause.

**The derived tests were committed wrongly at first.** All 37 landed in one commit, which would have put 21 red gate assertions into pull request 1 — a pull request that cannot satisfy them, gated by an unconditional required check. This is exactly what the apportionment in this file exists to prevent, and it was missed on the first pass. Undone before pushing; the gate group is held out and returns in the commit that wires the gate. `test-plan.md` records it.

## The record's own pull request

Task 13.3 asked for it, and it is opened immediately after the commit that writes this file — so it could never have been ticked here. It is recorded in prose for the same reason `refresh-readme-accuracy`'s task 8.6 is, one directory over: **a change's `tasks.md` ends at the archive commit.**

That rule is this change's own, written into `AGENTS.md` after 8.6 turned out to be the only reason that record was red. This change then broke it — 13.3 is an act that happens after the archive commit, and it went into the task list anyway.

What is worth recording is how it was caught. `openspec validate --archived`, the gate this change installs, ran on this branch and reported:

```
✗ change/2026-09-08-make-openspec-validation-a-usable-gate
  ✗ 3 incomplete tasks (34/37 completed)
```

Two of those were simply not yet ticked. The third was 13.3, and without the gate it would have merged unticked and this change would have joined the four records it was written to settle — red on arrival, in the archive, for the exact defect it diagnosed. The rule caught its author, and the check caught the rule being broken, before either reached the trunk.
