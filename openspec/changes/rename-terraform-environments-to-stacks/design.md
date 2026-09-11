## Context

`docs/naming-conventions.md` was recorded on 2026-09-11 and carries a banner saying it is not yet in effect. Four `docs/change-queue.md` entries bring the tree to it: 61 (this change) renames the axis, 62 renames the stacks and their Hetzner resources, 63 renames the external services, 64 moves the data mount. The document is the decision; this change is not the place to re-argue it.

What this change has to decide is narrower and entirely about **boundaries**: how far the word travels, what it must not touch, and how it interacts with the one other change currently in flight.

## Decision 1: Sequence this before entry 60, and say so

`docs/change-queue.md` entry 60 factors the four discovery bodies into one artifact under `.github/scripts/`. Entry 61 sweeps all four. Either order works and neither blocks the other; the recorded hazard is doing them in the same week without deciding which is first, because entry 60 must **replace** the identity assertion that makes running one discovery body evidence about all three, and a rename moving through those same bodies at the same time breaks that assertion twice from two directions.

**61 first.** Two reasons. It blocks 62, 63 and 64, and entry 60 blocks nothing. And a factoring is worth more when what it factors has stopped moving: entry 60 done first would be immediately followed by a rename sweeping the artifact it just created, while 61 done first hands entry 60 four bodies in their final vocabulary.

The cost of this order is the one entry 60 names — this change edits the same body four times rather than once. That is mechanical and the identity assertion catches a copy left behind, which is exactly the case that assertion exists for.

## Decision 2: How far the word travels

The path move is unambiguous. The word is not, because `environment` names three different things in this repository and only one of them is moving.

**The rule this change applies:** rename the word where it names **the unit the pipeline discovers, plans, applies, drift-checks and converges**. Leave it where it names a **GitHub Environment**, the **`environment` label** on a Hetzner resource, or the **environment axis** itself.

So `environments_root`, `matrix.environment`, `ENVIRONMENT_NAME`, `ENVIRONMENTS`, `REQUESTED_ENVIRONMENT`, the `discover`/`affected`/`planned` job outputs and `host-converge.yml`'s dispatch input all move.

Four things stay, and the fourth is the one a sweep gets wrong:

- `github_environment` and every `environment:` job key — they name a GitHub Environment.
- `environment = "prod"`, the label — it names the environment axis, and entry 62 spells its value in full.
- `ansible/inventory/prod.hcloud.yml` and `ansible/inventory/group_vars/prod.yml` — entry 62 renames those.
- **`target_environment` and `TARGET_ENVIRONMENT`.** This is a play input governed by *Host Configuration Names the Environment It Targets* (`openspec/specs/iac-host-configuration/spec.md`), and it names the Ansible group the play converges — an environment-axis handle with consumers in `ansible/playbooks/host-baseline.yml`, `.ansible-lint`, `.pre-commit-config.yaml` and `docs/bootstrap-a-new-host.md`. It is *derived* from the stack name today because the two coincide; after entry 62 the group is `production` while the stack is `main-production`, and re-deriving it is that entry's work, not this one's. So the assignment becomes `TARGET_ENVIRONMENT: ${{ matrix.stack.name }}` and carries a comment saying why the two names differ.

**The prose moves with the identifiers rather than being left behind.** The entry's own warning — that a directory called `stacks/` iterated by a variable called `environment` contradicts itself in one file — applies unchanged to a `stacks_root` whose refusal message says *"Environment discovery found no ..."*. It applies one layer further out to a requirement that obliges "every directory under `terraform/stacks/`" while calling the thing in it an environment. Half a rename leaves a reader unable to tell which word is load-bearing, and that is the defect, not the character count.

**Which requirements this selects, and why it is not the ones containing the path.** A first draft selected the twelve requirements whose text contains the string `terraform/environments`. That is a different and strictly smaller rule than the one above, and the difference is not cosmetic: *Scheduled Drift Detection* obliges a plan "against every environment" and names no path at all, so `drift.yml` would have iterated `matrix.stack` under a requirement still saying environment — the half-rename this change exists to avoid, one layer out. The rule above selects **twenty-two across six capabilities**, and it was applied by reading all **nine** in `openspec/specs/` rather than only the ones the proxy had already turned up — which is the second half of the same mistake, and the one a reader cannot otherwise tell from a deliberate exclusion:

- `iac-cicd-pipeline`, **nine** — the four carrying the path, plus *Credential Scoping by Privilege*, *Destroy Policy Gate*, *Serialized Terraform Runs*, *Scheduled Drift Detection* and *Host Configuration Is Applied by a Gated Workflow*. The last of those was an unarchived delta when this plan was written and reached `openspec/specs/` while the branch sat unrebased — see decision 4. Nine is what `docs/change-queue.md` entry 61's "roughly ten requirements" estimate was reaching for.
- `iac-safety-hardening`, **five** — plus *Automated Dependency Updates*, whose Terraform paragraph obliges that "adding a Terraform module or environment SHALL include adding it here", *here* being the Dependabot list this change edits.
- `iac-state-management`, **four** — plus *Workspace Execution Mode Set to Local* and *Each Environment Has a Dedicated Hetzner Cloud Project*.
- `iac-repo-foundations`, **two**.
- `iac-server-lifecycle`, **one**, and `iac-data-volumes`, **one**. Neither names the path; both name "the prod environment" and "the environment's variables and non-secret tfvars", which is the same `terraform/stacks/prod/terraform.tfvars` that *Version Control Excludes State and Secrets* now calls stack configuration. Left unswept, one file would be described in two vocabularies across three capabilities.

The three untouched are `iac-host-configuration` (its subject is the environment a play targets — the axis, not the unit), `iac-platform-services` and `iac-platform-deploy-pipeline` (their subject is the shared Compose stack on a host, which is a different thing that already owns the word — see the disambiguation the stack definition now carries).

The boundary is still **not** a licence to reword every requirement containing the word. *Data Durability for Stateful Resources* says "the prod server is created via `terraform/environments/prod/`"; there the word is a path component and the sentence is about a server, so only the path changes.

Three capability `## Purpose` lines carry the word too — `iac-repo-foundations`' "environment/module folder structure", `iac-state-management`' "each environment operates against" and `iac-data-volumes`' "Lets the prod environment provision" — and a requirement delta cannot reach them. Those three deltas therefore carry a `## Purpose` section, which archived changes in this repository already do. Whether `openspec archive` applies a `Purpose` to an **existing** capability rather than only to a new one is not established here; tasks.md 10.1 checks that it landed and corrects it in the archive commit if it did not.

## Decision 2a: `host-converge.yml` is discovery over the environment axis producing stacks, and both halves are named

This is the one body where the rule above has real work to do, so it is settled here rather than left to the implementer.

`host-converge.yml` enumerates `ansible/inventory/*.hcloud.yml` — not `terraform/stacks/*/` — and the `name` it derives reaches six surfaces: the `-i` inventory path, the `--vault-id` label, `-e target_environment=`, the concurrency group, `terraform/stacks/<name>/pipeline.yml`, and `ansible/inventory/group_vars/<name>.yml`.

**The discovered unit is the stack.** `docs/naming-conventions.md` derives the inventory source from the stack name (`ansible/inventory/main-production.hcloud.yml`), and what the row carries is that stack's GitHub Environment and its read-only secret, read out of that stack's `pipeline.yml`. So the matrix key, the job output and the dispatch input take `stack`, exactly as the other three workflows do, and its refusal messages follow.

**`target_environment` and the vault-id label are the environment half**, and they stay — per the fourth keeper above. They are derived from the stack name today and entry 62 re-derives them. Naming both halves is what stops the next reader concluding that one of them was missed.

`inventory_root` and `group_vars_root` stay as they are: they name directories entry 62 renames, and neither is the Terraform root.

## Decision 3: Names are not renamed here — neither requirements' nor scenarios'

Three of the twenty-two requirements carry *Environment* in their title. Renaming one is a `RENAMED` delta. It is deferred to entry 62 and recorded there, not only here, because a note kept inside this change is archived with it.

**Scenario names are not renamed either, and that one is enforced by the tool rather than chosen.** A `MODIFIED` requirement replaces its block whole, so `openspec validate` reads a renamed scenario as a *dropped* one and refuses:

    ✗ MODIFIED "Pull Request Plan Visibility" omits scenario(s) the current spec
      still has: "A shared module change is planned against every environment", …

This was found by running the validator against a first draft that did rename them, and it is recorded here because it is not obvious from the file format and because it bounds entry 62 in exactly the same way. Scenario **bodies** — the `WHEN` and `THEN` lines — are free to change, and they do.

The cost of both is a requirement and a scenario whose titles say *Environment* while the prose under them says *stack*, for as long as it takes entry 62 to land. That is visible and self-correcting rather than silent: the mismatch is in one line and the entry that fixes it names it. The cost of forcing it here is a delta that fails to apply on archive, in a repository where `openspec validate --archived` is being wired into the required check.

## Decision 4: The overlapping delta archived first; the sweep moved into this change's own delta

**This decision is now history, and it is recorded rather than deleted because what it produced is still here.** When this plan was written, `apply-host-configuration-through-a-gated-workflow` was at `ship` with an unarchived delta that `MODIFIED`s *Each Environment Declares Its Own Pipeline Configuration* — a requirement this change also modifies — and `ADDED`s *Host Configuration Is Applied by a Gated Workflow*. A `MODIFIED` delta replaces a requirement's body wholesale, so whichever of the two archived second would have overwritten the first. Of the three options open then — wait for that change to archive, note the reconciliation for whoever archived second, or sweep its delta so that both bodies said the same thing and the order of archive stopped mattering — this change took the third and swept it.

**That change archived first, and in its unswept form.** It reached `origin/main` as `3282bd0`, while this branch was still unpushed and unrebased, so the sweep never travelled with it. Its record now sits at `openspec/changes/archive/2026-09-11-apply-host-configuration-through-a-gated-workflow/` saying `terraform/environments/`, over a tree that still says `terraform/environments/`. That is consistent and needs no repair.

**The sweep of that record is therefore dropped rather than carried forward.** An archived change's record may be corrected only to make it say what actually happened, and what happened is that the change was planned, built and archived while the directory was called `terraform/environments/`. Rebasing onto the archive re-applied this branch's edit through git's rename detection, into `openspec/changes/archive/2026-09-11-…/specs/iac-cicd-pipeline/spec.md`; it was reverted deliberately, and a reviewer should expect that file to be absent from this change's diff. Nothing warned about it: the rename detection resolved what would otherwise have been a modify/delete conflict, so the rebase reported success.

**What the collision leaves behind is one extra requirement to sweep.** Archiving merged that change's `ADDED` requirement into `openspec/specs/iac-cicd-pipeline/spec.md`, where *Host Configuration Is Applied by a Gated Workflow* is now live in the old vocabulary. Decision 2's rule selects it — it governs `host-converge.yml`, whose matrix key, job output and dispatch input this change renames — so it becomes this change's **twenty-second** `MODIFIED` requirement. Its body is the text this branch had already swept, lifted from the pre-archive delta before that edit was dropped and verified byte-identical, unswept, to what archiving actually merged. Its scenario titles are left alone, per decision 3.

**The order-of-merge constraint this decision originally recorded still holds**, and is now the only part of it that constrains anything: **this branch must not merge in its plan-and-tests state.** That would put swept delta text on the trunk over a tree that has not moved, and nothing detects it — `.github/tests` reads `openspec/` only for the citation-form check and never compares a cited path against the tree, and `openspec validate` checks structure rather than paths. Recorded as tasks.md 7.3.

## Decision 5: The move is `git mv`, and what `git mv` does not move is written down

`git mv terraform/environments terraform/stacks` moves tracked files. `terraform/environments/prod/` also holds an untracked, gitignored `.terraform/` — the provider directory `terraform init` created — and the repository-root `.envrc` is prod's local read-only-token file, pointing at a path that is about to change.

Neither appears in the diff, so review cannot catch either. The consequence is local-only and loud rather than silent (`terraform validate` fails with an uninitialised backend), but it is the kind of thing a session resuming this tree loses an hour to. It is recorded as a task rather than as a comment in a file nobody will open.

## Decision 6: Verification is `.github/tests` plus `terraform validate`, and nothing else is claimed

This change touches no Terraform module and no Ansible role, so of the three test commands in `AGENTS.md` only the third applies: `python3 -m unittest discover --start-directory .github/tests`, whose test-path glob is `.github/tests/*.py`. The baseline on trunk `74ea5b9` is **712 tests, green**, recorded here so that a run afterwards is a comparison rather than an assertion. It was **601 on trunk `032f923`** when this was drafted; three of main's own continuous-integration changes landed between, so the figure was re-measured rather than carried forward, in a throwaway checkout of trunk. Taking it by moving the derived module aside in the working tree instead makes three of `test_ci_configuration`'s repository-wide credential scans fail — `tracked_files()` raises rather than scanning around a tracked path that is absent — which is the suite behaving as designed and is recorded in `test-plan.md`.

`terraform init -backend=false && terraform validate` in each moved directory is the second half, and it establishes what the suite cannot: that the configuration still resolves from its new path. `-backend=false` is what the pipeline's own validate step uses and is what makes the check runnable with no HCP credential.

`pre-commit run --all-files` is the third, and a grep over the tree is the fourth — the grep is what distinguishes a sweep that is complete from one that is mostly complete, since a stale occurrence in a comment or an error message fails nothing.

**How the suite finds the body it executes matters to where the effort goes.** `.github/tests/test_environment_agnostic_pipeline.py` locates the shared discovery body **by shape** — the `run:` step containing the `terraform/environments` literal, carrying `GITHUB_OUTPUT` and free of Actions expressions — and its own docstring records that a name-based locator was tried and was wrong. So the literal the locator keys on is the path, not the step name; an implementer who renames only step names has moved nothing the locator reads, and one who renames the path has moved the thing it does. The same inaccuracy ("by step name") is in `docs/change-queue.md` entry 60 and is corrected there by task 7.1.

What is **not** established locally, and is stated rather than implied: that the workflows still run. `actionlint` is on no path in this environment and `docs/change-queue.md` entry 6 owns adding it. What stands in for it is that the suite parses every workflow with PyYAML and executes the discovery bodies against scratch trees — which reaches the bodies this change edits, and does not reach expression syntax or `needs:` references. One such reference is checked statically all the same: `.github/tests/test_planned_environment_apply_stage.py` asserts that every `needs.<job>.outputs.<name>` read in `apply.yml` names an output that job publishes, so renaming the `environments` output there cannot silently yield an empty matrix. `drift.yml` and `pr-validation.yml` have no equivalent, and a missed reference in either surfaces as a failing job in CI rather than as a silent skip. The first pull request is what exercises the rest.
