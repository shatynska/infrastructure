# Design

## Context

`close-ci-verification-gaps` put the Molecule suite in continuous integration as `ansible-verify.yml` and deliberately left it advisory. Its `proposal.md` and `design.md` both name the reason: the suite had never run outside a developer machine, and its scenarios manipulate UFW, `fail2ban` and `systemd` inside containers on a runner that is itself containerised. Making it blocking on day one risked making `main` unmergeable for a reason unrelated to any change under review. `docs/change-queue.md` entry 4 recorded the promotion and what it would take.

This change is that promotion. It is a workflow-design change with a settings edit at the end, not a settings edit.

### The evidence the advisory tier was collecting

Five workflow runs, read from the forge rather than recalled:

| Run | Branch | Trigger | Conclusion |
|---|---|---|---|
| 34045404326 / 34046099603 | `close-ci-verification-gaps`, then `main` | pull request, then dispatch | failure — one scenario's own assertion |
| 34057674462 | `pin-and-fix-molecule-suite` | pull request | success |
| 34058142743 | `main` | dispatch | success |
| 34120667954 | `fix-volume-discovery-and-consistency` | pull request | success |
| 34144599475 | `reclaim-superseded-app-images` | pull request | success |
| 34156283803 | `decide-archived-change-reference-policy` | pull request | success |

The first pair established the thing the advisory tier existed to establish: the privileged-systemd scenarios, UFW and `fail2ban` all converge and verify on a hosted runner. Their single failure was a defect in a scenario's own assertion, fixed by `pin-and-fix-molecule-suite`, and it was deterministic across two independent runs rather than flaky.

The last three are green on three *different subjects*, none of which is the suite itself. `docs/change-queue.md` entry 4 point 1 asks for exactly that and warns against reading one subject observed twice as two observations. Three subjects, one observation each, satisfies it as written.

### What the promotion costs, measured

On the most recent run, all five roles green:

| Job | Wall clock |
|---|---|
| discovery | 4s |
| the longest role | 6m00s |
| the whole workflow | 6m11s |

Five roles summing to roughly twenty minutes of compute finish in six, because the matrix is parallel with `fail-fast: false`. Against `validate`'s 1m37s that is a real difference — but it is a difference **already paid** on every pull request touching `ansible/`. Nothing about promotion makes an Ansible pull request slower. What promotion changes is whether a red run blocks the merge.

The cost lands entirely on pull requests that touch nothing under `ansible/`, and only if the design is wrong. Decision 1 is about keeping it at four seconds.

## Decisions

### Decision 1 — Remove the workflow-level filter; gate inside an always-running job

**The filter cannot stay.** `openspec/specs/iac-cicd-pipeline/spec.md`, *Required Status Checks Report on Every Pull Request*, states it directly: a workflow-level `paths` filter on a required check never reports for non-matching pull requests, leaving them permanently pending and unmergeable. The workflow's own top comment says the same, and `pr-validation.yml` carries the shape that satisfies it.

**Deleting the filter and stopping is the trap.** Discovery enumerates roles from the repository, not from the diff. With no filter and no replacement gate, every pull request would start the full matrix — six minutes of containers for a typo fix, forever. That is precisely the outcome the operator's first question was about.

So the filter moves *inside*: a `dorny/paths-filter` step in the discovery job, matching `ansible/**`, whose output conditions the matrix job. Same action, same `ansible:` pattern, same job-internal position `pr-validation.yml` already uses for its own Ansible steps — one mechanism in the repository rather than two. The version is taken **from** `pr-validation.yml` rather than chosen: two pins of the same action are two things to update, and the argument for reusing the mechanism is the argument for reusing its pin.

The step reads which files a pull request touched, which on this event is an API read, so the discovery job declares `pull-requests: read`. A job-level `permissions:` block **replaces** the workflow-level one rather than adding to it, so the block must carry `contents: read` too or the job's own checkout loses its scope — `pr-validation.yml`'s `validate` job redeclares `contents: read` beside its `pull-requests: write` for exactly that reason. It belongs on the job rather than the workflow: *Least-Privilege Workflow Permissions* obliges each job to declare only what it requires, and neither the matrix job nor the aggregating job requires either. Nothing gains a write scope, and the credential prohibition in the Ansible requirement is untouched — `GITHUB_TOKEN` is not a production credential and is the only token in the workflow.

The filter step itself is conditioned on the event being a pull request. It resolves a diff, and on any other event there is none to resolve against; what the action does in that position is not something this repository has observed, because the workflow it is borrowed from runs on `pull_request` only. Skipping it outright is both the smaller assumption and the reason the polarity hazard in Decision 4 is unreachable rather than merely handled: with no filter output to misread, the resolution below has one branch on a dispatch, not two.

**Rejected: `paths-ignore` instead of `paths`.** It is still a workflow-level filter. The requirement forbids the mechanism, not one spelling of it, and the existing test asserts both keys.

**Rejected: a separate reusable "changes" workflow.** One more file and one more indirection to express a step that already exists twice in this repository.

### Decision 2 — Discovery runs unconditionally; only the matrix is gated

Discovery is a checkout and a `find`: four seconds, measured, no toolchain install, no container. Conditioning it would save nothing and would cost the property that makes it worth having.

That property is in `openspec/specs/iac-cicd-pipeline/spec.md`, *Ansible Configuration Is Verified in Continuous Integration*: discovery SHALL fail loudly rather than succeed vacuously. Leaving it unconditional means a repository state in which no role carries a `molecule/` directory fails **every** pull request, not merely the ones that touch `ansible/`. Under an advisory workflow that would be noise. Under a required check it is the correct alarm: the suite standing between a merge and production has silently vanished, and the pull request that removed it is not the only one that should stop.

It also keeps the conditional logic to one place. Gating discovery too would mean the "found nothing" branch and the "not asked to look" branch both produce an empty result, and the aggregating job could no longer tell them apart from the outputs alone.

### Decision 3 — A fixed-name aggregating job is the required context

GitHub matches required status check contexts against **job names**. The Molecule job's name is generated from the matrix, so its contexts vary with whatever discovery returns. Three consequences, and each on its own is disqualifying:

- The contexts cannot be enumerated in branch protection in advance.
- A role added under `ansible/roles/` would introduce a context nobody registered — the check would run and not be required, silently.
- Under an empty or skipped matrix, **no context appears at all**, which under branch protection is a required check that never reports: the same permanent pending this change exists to remove, reintroduced one layer down.

So a job named by a literal — `ansible-verify` — depends on both other jobs, runs `if: always()`, and is the single context registered. The matrix jobs stay visible on the pull request and stay unregistered.

**Rejected: registering the discovery job instead.** It concludes before any scenario runs. A required check that is green while the suite is still running, or has failed, is worse than no check.

### Decision 4 — `skipped` is not `success`

The aggregating job's whole content is refusing one conflation. `if: always()` plus `success()` reads a skipped need as satisfied, and `needs.<job>.result` returns `skipped` for a job whose `if:` was false **and** for a job whose matrix was empty. The discovery step's own comment already names this hazard at its own layer: *"an empty matrix skips the dependent job and the workflow concludes success having run nothing, which is a green that verified nothing."*

The gate therefore reads three inputs and decides explicitly:

| Discovery | Ansible changed | Matrix result | Verdict |
|---|---|---|---|
| not `success` | any | any | **fail** — discovery is the gate's own precondition |
| `success` | `true` | `success` | pass |
| `success` | `true` | `skipped` | **fail** — the vacuous green |
| `success` | `true` | `failure` / `cancelled` | **fail** |
| `success` | `false` | `skipped` | pass — nothing under `ansible/` changed |
| `success` | `false` | `success` | pass |
| `success` | `false` | `failure` / `cancelled` | **fail** |

Discovery is checked **first**, and not merely for tidiness: when discovery fails, its outputs are empty strings, so the "Ansible changed" input is `''` and the matrix result is `skipped` — a combination the table's fifth row would otherwise pass. The gate would report success precisely when discovery had refused to.

**Where the "Ansible changed" input comes from is its own hazard.** Change detection resolves against a pull request's diff. A `workflow_dispatch` run has no diff; Decision 1 therefore skips the filter step entirely on that event, and a resolution step supplies `true` in its place. Defaulting it to `false` instead — the shape that falls out of simply reading an absent output — would skip the matrix and pass, a green conclusion on the exact trigger this repository uses to run the suite against the trunk, and the trigger two of the runs in the evidence table above came from. With `true` supplied, the table's rows five to seven are unreachable on a dispatch by construction.

That resolution is a **second** script, not a row of this table: this table takes "Ansible changed" as given and decides what to conclude from it, while the resolution decides what that input is. Decision 5 covers both, separately — conflating them is how the polarity ends up asserted nowhere, each test assuming the other checked it.

**The resolution refuses a value the filter did not produce.** On a pull request the filter step must have run, so anything but `true` or `false` means it did not, and the empty string a skipped step leaves behind is refused rather than read as `false`.

This is not defensive padding; it is what makes the filter step's condition safe to reason about. Read as `false`, that empty string skips the matrix and the gate concludes success on a pull request nothing verified — and **narrowing** the condition produces it exactly as surely as inverting it does. A plausible-looking `&& github.actor != 'dependabot[bot]'` would silently green every Dependabot pull request, which is why it cannot be left to an assertion about how the condition is spelled: such an assertion must either reject conditions that are fine or accept ones that are not, and a review that suggested that very conjunct as a harmless example is the evidence that the trap is easy to walk into.

With the refusal in place the whole class is loud. Every mis-condition on that step — inverted, widened, narrowed, or removed — now either fails the static checks or fails the run, and none of them reports success having verified nothing. That is the property worth having; the static assertions catch the two unambiguous cases and are not asked to carry the rest.

`cancelled` is failed rather than ignored. A cancelled run has not verified anything, and `concurrency.cancel-in-progress` cancels a *superseded* run whose checks belong to a superseded commit, not to the one being merged.

### Decision 5 — The gate's script carries no `${{ }}`, so it can be executed in a test

The suite already exercises the role-discovery snippet by pulling its `run:` text out of the workflow YAML and running it under `bash` against a scratch tree, and asserts the snippet is free of `${{ }}` so that this is possible. `close-ci-verification-gaps` chose that shape deliberately.

The gate gets the same treatment: its three inputs arrive through the step's `env:` block, where the expressions are evaluated, and the script reads environment variables. The test then runs it once per row of Decision 4's table — all seven, four refusals and three passes, rather than the subset a scenario list happens to name.

The change-detection resolution step is written the same way and tested separately, over the event name rather than over the table. Two scripts, two tests: the resolution's only interesting case is the one Decision 4 calls the polarity hazard, and it is invisible to a test that feeds the gate its input directly. This is the difference between asserting that the gate exists and asserting that it discriminates — the standard this repository applies to its own destroy gate and its own secret scanning.

**Rejected: extracting the gate into `.github/scripts/`.** That is `docs/change-queue.md` entry 6's second bullet, deferred there on merit-vs-scope grounds for the destroy gate's inline shell. The extract-and-run pattern gets the same executable coverage without adding a file or pre-empting that decision.

**Rejected: expressing the gate as a GitHub Actions `if:` expression.** It would be untestable by anything in this repository, and the conflation Decision 4 exists to refuse is a property of those very expressions.

### Decision 6 — Branch protection is operator-applied, and the tests say so

`.github/tests` may make no network call — `openspec/specs/iac-cicd-pipeline/ spec.md`, *The Continuous-Integration Configuration Is Itself Verified*, requires it and the suite asserts it of itself. So nothing in this repository can verify that `ansible-verify` is registered in `main`'s required contexts. Whatever the suite asserts is about the workflow file.

What it *can* assert is everything that makes registration possible and safe: the workflow carries no workflow-level path filter, the aggregating job's name is a literal rather than an expression, that job depends on the matrix, and its gate discriminates. Registration itself is a repository setting the operator applies, and the tests must not read as though they had checked it — a green suite implying more than it checked is the failure mode this capability names repeatedly.

Branch protection as it stands, read from the forge on 2026-09-07:

```
contexts: ["validate"]   strict: true   enforce_admins: true
required_approving_review_count: 0   allow_force_pushes: false   allow_deletions: false
```

`strict: true` means an Ansible pull request re-runs the suite after each trunk update. That is the existing cost of `validate` applied to a longer check, and it is accepted rather than worked around: the alternative is merging Ansible changes against a trunk they were never verified against.

### Decision 7 — The specification changes in four places

- ***Ansible Configuration Is Verified in Continuous Integration.*** The "Advisory tier" paragraph and the scenario *A failing Molecule scenario does not block a merge* both assert the opposite of what this change delivers. They become a second blocking tier and its inverse scenario. The tier labels change with them: *Blocking tier* and *Advisory tier* distinguished the two by whether they gate, which is no longer the distinction, so they become *Lint tier* and *Suite tier* — named by what they run, which is what still separates them. Everything else in that requirement — discovery, `--all`, the loud failure, digest pinning, the Galaxy exclusion, the credential prohibition — is carried through unchanged.

  It is the one delta that is **not** MODIFIED, and the reason is a tool constraint worth recording rather than working around silently. OpenSpec refuses a MODIFIED block that omits a scenario the current specification still has — the guard exists to catch a scenario lost by accident — and it follows a rename through to the block being renamed, so rename-then-modify does not escape it either. Removal plus re-addition under a different name is what the tool supports for a deliberate drop, and the two names must differ or the delta is rejected as present in both sections. Hence *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge*: the new name states the obligation that changed, and the pair reads as a replacement in the specification's own history rather than as a deletion.
- ***Required Status Checks Report on Every Pull Request.*** Written in Terraform terms: "the pull request check", singular, and "pull requests that touch no Terraform files". Generalising it to every workflow registered as a required check is the requirement this change is an instance of, so it is modified rather than duplicated — and the existing test that asserts it becomes a check over a set of workflows rather than over one.
- ***Branch Protection on the Default Branch.*** It says "the validation workflow's status check SHALL be required". There are now two, and which contexts are registered is the deliverable of this change that lives outside the repository. Naming them is what makes the operator's edit reviewable.

  While the requirement is open, it is also brought up to date with the rest of what was applied on 2026-09-07 and read back from the forge above: `allow_deletions: false`, `strict: true` and `enforce_admins: true`, none of which the requirement mentioned — the last of these being what the Risks section below turns on, since it is why de-registering the context is the only rollback lever. Recording settings that already hold is not a new demand on the operator — it closes the gap between a requirement and the state it describes, which is the gap this requirement spent its whole life in while no protection existed at all.
- ***Gated Production Apply Applies the Reviewed Plan.*** It carries the cross-reference "The workflow that is registered as a required check SHALL NOT be path-filtered at the workflow level", explaining why the *apply* workflow may carry a filter. The sentence stays true of each workflow, but its singular is what this change makes false. Left alone, the capability would describe the same fact in the singular in one requirement and the plural in another, and a reader reconciling them would have to guess which is current.

**A bounded interval this creates.** Between the implementation merge and the archive merge, the workflow comment and two test docstrings cite *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge*, a requirement name that does not exist in `openspec/specs/` until the record lands. `AGENTS.md`'s citation rule accepts exactly one such interval — a change introducing a new capability — and this is not that, though it is the same shape and the same bounded duration, and the executable check matches path form rather than requirement names, so nothing fires. It is knowing and it closes at archive; the alternative is citing a name that will be wrong afterwards, which is the rot the rule exists to prevent. Recorded so a later reader does not read it as an oversight.

### Decision 8 — A per-scenario matrix is out of scope

`molecule test --all` runs a role's scenarios in sorted order and stops at the first failure; every scenario sorting after it is neither executed nor listed in the SCENARIO RECAP. Molecule's own `--continue-on-failure` is unavailable here — it applies only with `--workers`, and `--workers > 1` requires collection mode, which these plain roles are not. A matrix over scenarios rather than roles is the remedy, and it would parallelise the longest role as a side effect.

It is not folded in. It rewrites discovery's output shape, the matrix job's identity, and every test that asserts either — and it changes what a role's job *is*, which would land in the same diff as the change that decides which job is required. The promotion does not depend on it: an aborted red run is still red, and still blocks. Under-reporting makes diagnosis slower, not the gate weaker.

Recorded in `docs/change-queue.md` as an entry of its own, because entry 4's paragraph about it is deleted when this change is archived.

## What was observed

Recorded here because a change is delivered when its effect is observed, not when its pull request merges. All three observations were made on 2026-09-08, after #72 merged as `7ea8dec` and `ansible-verify` was registered.

**Branch protection, read back from the API rather than assumed:**

```
contexts: ["validate", "ansible-verify"]   strict: true   enforce_admins: true
allow_force_pushes: false   allow_deletions: false
```

Both contexts carry `app_id: 15368`, so only GitHub Actions can satisfy them. The registration was applied through the `required_status_checks` sub-resource so that nothing else in the protection object was touched.

**A pull request touching nothing under `ansible/` reports without working.** Pull request #72, its own first observation: `discover` 5s, the matrix **skipped**, `ansible-verify` success 4s. Twelve seconds and no container. The log carries the decision rather than only the outcome — *"Pull request: the change filter reported 'false', so run-suite=false"*, then *"Nothing under the configuration directory changed, so the suite was skipped rather than run. Concluding success having correctly done no work."*

**A run with no diff verifies the whole suite.** Manual dispatch on `main`, [run 34183298612](https://github.com/shatynska/infrastructure/actions/runs/34183298612): all five roles ran, 6m57s, green. *"Event 'workflow_dispatch' carries no diff to filter on, so the whole suite runs: run-suite=true."* This is the path Decision 4 argues about and no test can reach, and it is also the first time anything in this repository has observed the change filter being skipped on a diffless event — an assumption the plan review flagged as unsupported.

**A failing scenario blocks the merge.** A throwaway pull request, #73, added one failing assertion to a single scenario and was closed unmerged once the observation was made. `molecule (docker)` red, the other four roles green so `fail-fast: false` held, `ansible-verify` red, and the pull request `BLOCKED`. `validate` stayed green, so the block is attributable to the Molecule suite alone. The gate refused with its three inputs visible — `DISCOVER_RESULT=success MATRIX_RESULT=failure RUN_SUITE=true` — and named the row: *"The suite concluded 'failure' (run-suite=true). Only 'success', or a skip on a run that did not ask for the suite, may conclude success."*

That is row 4 of Decision 4's table firing in production, and it is the effect this change exists to produce. No part of the gate was waived.

## Risks

- **A promoted check turns out to be flaky under load.** Three independent green runs is evidence, not proof, and hosted-runner containers are a shared resource. Mitigation is that the failure is loud and reversible: removing one context from branch protection restores the advisory tier in seconds, with no code change. That is the same lever that made this promotion a settings edit in the first place, and it works in both directions.

  It is worth being plain that it is the **only** lever. `enforce_admins: true` means there is no per-merge override for anyone, so a flaky check blocks every Ansible merge until the context is de-registered. That is the intended property of `enforce_admins` rather than a defect of this change, but it changes the shape of the recovery from "an admin merges this one" to "the operator edits the setting".
- **Discovery fails for an environmental reason** — a checkout failure, an API permission gap, an outage in the change-detection action. Every pull request in the repository is then blocked, doc-only ones included, because the gate fails closed on a non-`success` discovery. That is the correct behaviour under Decision 4, and the coupling is not new — `pr-validation.yml` already blocks everything if its own job cannot run — but promotion adds a second job that can fail this way. Accepted rather than mitigated: a gate that opens when its own precondition is unavailable is the "could not tell, therefore fine" shape this capability refuses everywhere else.
- **The gate passes for the wrong reason.** Decision 4's table has seven rows and four of them are refusals; a gate written by hand from that table can disagree with it. This is why the gate is executed in a test rather than grepped — Decision 5.
- **Discovery's unconditional failure blocks unrelated work.** Decision 2 accepts this deliberately. It can only fire when no role under `ansible/roles/` carries a `molecule/` directory, which is not a state this repository reaches by accident.
- **The operator's settings edit is forgotten.** The change then ships a correctly-shaped workflow that is still advisory — the status quo, not a regression. It is the confirmation step of this change's own `ship` stage, and the observation is a direct read of the protection API.

  This is why the workflow's top comment and `README.md` say the `ansible-verify` job is *the context to register* rather than that it *is* registered, and point at the protection API for the answer. A sentence asserting the registration would be false from the moment this merges until the operator applies the edit — and would stay false, silently, in exactly the case this risk describes. Unlike the citation interval recorded under Decision 7, this one does not close on its own.
- **A pull request open at the moment of registration looks stuck.** Registering a context does not retroactively produce one on a head commit that predates it, so any open pull request shows `ansible-verify` as expected-but-never- reported until a run is triggered on its head. `strict: true` already forces an update-branch before such a pull request can merge, and that push produces the run, so the state resolves on its own. It is called out because it is the first thing the operator will see after making the edit, and it reads exactly like the permanent-pending failure this change exists to prevent.
