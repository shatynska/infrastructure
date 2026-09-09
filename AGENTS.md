<!-- ai-toolkit:development-workflow v3 -->
<!-- Generated. Do not edit inside this block — it is replaced on update.
     Project-specific conventions belong below the closing marker. -->

## Development workflow

The unit of work is a **change**: a feature, a modification, or a decision with design content, carried from proposal to record. These rules describe its life in three stages — `plan`, `build`, `ship` — and what holds throughout.

Work too small to be a change — a typo, a one-line correction with nothing to specify — skips `plan`. It does not skip `ship`: nothing reaches production except by merging.

These rules assume this project has a remote, pull requests, continuous integration, a deploy triggered by merging to the trunk, and OpenSpec for its change records, and that more than one session may work on it at once.

### Your branch and working tree

A change gets one branch and one working tree and keeps both from proposal to record. Cut the branch from the freshly fetched trunk; put the working tree at `.worktrees/<name>`.

_Claude Code binding:_ `EnterWorktree` places working trees under `.claude/worktrees/` and will not enter one elsewhere.

Several sessions may work on one change, one after another and never at the same time. A session resuming a change enters the working tree that change already has.

Fetch the trunk periodically throughout, and bring it into the branch rather than meeting it at the pull request. Before the branch is pushed, rebase onto it. After, merge it in: a rebase then needs a force push over a branch under review, where a merge does not.

**Provision before relying on any verification result.** A new working tree carries tracked files only: no ignored configuration, no installed dependencies, no build artifacts, no share of external state. **Verification that cannot reach what it needs skips and reports success rather than failing**, so an unprovisioned run is indistinguishable from a passing one. Until provisioning is complete, report verification as **not run, and why**.

Provisioning is complete when every step this project names has been reached, not the first. Reach that state rather than asking whether an earlier session already did; each step is safe to repeat.

**Where verification writes to a shared service, take your own namespace within it**, named deterministically from your working tree, and bring it to the project's initial state whether or not one already exists under that name. Check for the service before reporting it unavailable. Nothing here reclaims a namespace; they accumulate.

Where this project binds these two rules to a particular service, the binding is an adjacent section of this file; read it as part of them.

### Reporting where the change stands

On entering a working tree, before anything else, and again as the last thing said before stopping, report the change's status as one line, in this exact form, with `|` as a plain-text field separator without header rows:

`| <change> | <stage> | <task progress> | <commits> |`

For example: `| some-change | plan:explore | 0/0 | 1 |`

Each field is a short value, not a sentence — nothing else belongs on that line.

Derive the report from the repository where you can — the change's own artifacts, the commit log, the forge, and an actual run of the verification. Where a fact is in none of them, ask rather than assume it.

**The stage names a state, never an act.** The acts are the transitions between them, and the sections below walk them in order — some together, where one act follows another with no decision in between:

```
plan:   explore · draft · review · fix · approve · commit · derive tests
build:  apply · verify · review · fix
ship:   open pr · merge · deploy · confirm · archive
```

A state is `<family>:<transition>ing` while that transition runs and `<family>:<transition>ed` once it has happened — `plan:drafting`, `build:applying`, `plan:approved`, `ship:merged`. Two reorder: `plan:tests-derived` and `ship:pr-open`. Add `blocked:<what>` and `abandoned` at any point.

Always write the family prefix: `plan:reviewing` and `build:reviewing` dispatch different reviewers.

### plan

**explore** — a change with no proposal yet. Auxiliary artifacts such as a handoff may exist.

**draft** — use a specification-driven change process for non-trivial features, changes and significant architectural decisions. Do not begin implementing without a proposal recording what is intended and why. A change's artifacts are read before implementation, not written afterwards to describe what was done.

**review → fix → approve** — dispatch review against the complete artifact set, never a package still being written. Fix and re-review until the verdict permits proceeding, bounded at six rounds; on reaching it, report where the loop stands and what is outstanding, and ask before continuing. A conditional pass is permission conditional on the fixes it names: apply them and continue without a further round. Where the reviewer judges the concept unsound rather than the artifacts defective, stop and raise it immediately, whatever the count.

_Claude Code binding:_ dispatch `ai-toolkit:change-plan-reviewer` once every artifact the change calls for is complete. Do not use `/code-review` for this gate — it reads a diff, and at this point there is none. On `FIX REQUIRED` fix and re-dispatch; on `CONDITIONALLY APPROVED` apply the `[MINOR]` fixes and continue; on `APPROVED` continue; on `REJECTED` stop and raise it.

**commit** — suggest committing the approved plan before tests are derived from it; the tests map to that baseline. Where the commit is declined, report that the next step is blocked on it and stop there, rather than proceeding without it.

**derive tests** — have an author other than whoever writes the implementation derive tests from the approved specification deltas, not from implementation code. That author needs this project's test command and test-path glob; both are in this project's own conventions.

A stated exemption applies where this project's rules name one for a class of change, and the reason is given when it is used. A change declaring no specification deltas owes no new tests, only that the suite stays green.

_Claude Code binding:_ dispatch `ai-toolkit:change-test-writer` after the verdict permitted proceeding, any conditions were applied and the plan was committed — and before implementing.

### build

**apply** — implement only once two things hold: a commit holding the approved plan, which follows the verdict that permitted proceeding, and the derived tests — or the stated exemption that excused them. Where either is absent, take the missing step rather than starting and noting the gap. Work too small to be a change skipped `plan` and has neither to hold.

**verify** — run the verification relevant to the change: tests, type checking, linting, formatting, a build, whatever this project's conventions require. Do not report a change as complete without having run it.

**review → fix** — have an independent reviewer read the diff against the change's own specification: each requirement implemented, the implementation matching what the specification describes, the derived tests covering what changed, no unrelated scope, this project's conventions followed. This review reads code; the review in `plan` reads artifacts.

Dispatch against a diff that already passes verification. Re-review only where the fixes were substantial enough to warrant it, bounded at three rounds; past three, report where the loop stands and ask rather than dispatching a fourth. A review judging the implemented change unsound rather than defective exits immediately and is raised.

_Claude Code binding:_ run `ai-toolkit:change-code-reviewer` over the change's diff.

### ship

Nothing ships from a local machine. Never run the deploy command against production — a change reaches production by merging and by nothing else. Local credentials for production, where they exist at all, are for reading — a plan, a status, a log — and not for applying.

Every change reaches the trunk through pull requests, and takes at least two. Begin once verification passes on the branch head and `build`'s review has cleared.

**open pr → merge → deploy** — open the pull request, let continuous integration run, and wait for the operator's confirmation that it merged and that the deploy is healthy. Do not infer a merge, a deploy or a confirmed effect from a green pull request, an approval, or silence.

**confirm** — a healthy deploy is not the change working. Propose how the effect can be observed — what to look at, what provokes it, what result would mean it worked — and wait for the operator's confirmation.

Two classes cannot answer that gate and are waivable. Say so plainly, name the class, and wait for the operator to waive it; record the waiver in the change's own artifacts — the record is archived on the strength of it, and waiving your own gate is not the confirmation this step exists to obtain. Where a successor is intended, the waiver names its change-queue entry or the branch it was opened on:

- no observation can actually be made — a refactor, a dependency bump or an internal cleanup with no externally observable effect, and equally an observation you proposed that turns out not to be performable;
- a change that was the wrong change: its observation was made, its effect is absent, and it is not to be corrected in place.

A recorded waiver completes **confirm**: `ship:confirmed` is true of a waived change.

**archive** — once the effect is confirmed or the gate waived, bring the branch back to the freshly fetched trunk, commit the change's specification record there, and open a pull request for it: the last of the change's pull requests. The work is on the trunk by now, however it was merged, so bringing the branch back to it discards nothing.

Two is a floor. Where the deploy is unhealthy, or the effect is absent through a defect, the change is not delivered and its record is not written: fix it and re-enter at `build`'s review gate; the fix takes a pull request of its own.

**then remove the branch and the working tree** — once the record has reached the trunk through its own pull request, every other pull request the change opened has merged, and nothing uncommitted or unpushed remains. **Read a merge from the pull request's state, not from branch ancestry** — a squash or rebase merge leaves no ancestry to read.

An abandonment recorded in the change's own artifacts, stating that the change is abandoned and its work not wanted, replaces both merge conditions and the unpushed one, but not the uncommitted one. Commit the record before reading the gate.

Remove the branch locally and on the remote, and the working tree from the repository's main working tree rather than from inside the tree being removed. Nothing here removes the namespace.

### Throughout

**Commits.** Prefer small, focused commits over large ones bundling unrelated concerns. After a meaningful milestone, proactively suggest a commit rather than waiting to be asked. Before committing: look at the diff, run the verification relevant to what changed, and check that no secret or unintended file is included. Suggest the commit; do not make it without confirmation.

While applying, the derived tests fail by design until the implementation is complete, so the verification above cannot pass and a hook running it blocks the commit. Commit with `--no-verify`, and read that failure as expected rather than as a defect. It suspends the pre-commit check, not the gate: `verify` still runs before any completion claim.

**Scope.** Prefer changes small enough to review in one sitting; where one grows to cover multiple independent concerns, consider splitting it. Implement only what belongs to the change in progress — an improvement noticed along the way becomes a separate proposed change rather than being folded in.

**A second change surfacing.** You work on one change at a time. Record the second before doing anything else about it.

- Where the change in progress **depends** on it: record the dependency and the wait in the current change's own artifacts, then at most open the identified change and recommend it be continued in a separate session.
- Where it **does not**: record it in `docs/change-queue.md`, creating that file if absent, or open the identified change.

*Opening* one means a branch of its own and a `handoff.md`, with no proposal — why the change was identified, what bears on it, and what it must not undo. Place it in the new change's own directory in this project's change-record layout — for OpenSpec, `openspec/changes/<name>/handoff.md`. The session that takes it up writes the proposal. Propose committing that branch at once; where the commit is declined, say that the handoff is unsaved and stop, rather than continuing and leaving it to be lost.

Such a branch is created and left: it takes no working tree and does not become the branch this session works on.

`docs/change-queue.md` holds identified changes, deleted when archived; an entry there is the separate proposed change the scope rule calls for, recorded rather than opened. `docs/deferred-work.md` holds what this project has deliberately not done, deleted when it stops being true.

Both sit outside the change that recorded them, because a note kept inside one is archived with it: it is the change succeeding, not the session ending, that would lose it.

**Assumptions.** Do not silently invent a requirement that was not stated and cannot reasonably be inferred; where an important decision cannot be inferred, ask rather than guess. Record significant decisions in this project's own artifacts rather than in conversation history alone.

**The repository is the source of truth.** Do not rely on earlier conversation context for information the repository itself can supply. Prefer reading a file, a spec or a commit over recalling what a previous exchange said about it.
<!-- /ai-toolkit:development-workflow -->

## Project conventions

These are specific to this repository, not part of the generated workflow block above. For the reasoning behind them, see `openspec/changes/archive/2026-08-18-project-foundation/design.md`.

### Production changes never bypass the pipeline

`terraform apply` is never run locally against `terraform/environments/prod/`. Production changes reach Hetzner only through the gated GitHub Actions pipeline: a PR-time plan for review, then a human-approved apply of that exact saved plan on merge to `main`. Local runs use the read-only Hetzner token and are for `terraform plan`/`validate` only.

### Task lists, archived records, and disclosing what was not done

This repository is wiring `openspec validate --archived` into the required pull-request check, so that an archived change whose task list still records outstanding work fails the pipeline. Three rules keep that gate honest, and **how much of each is machine-checked differs** — stated here because a rule that reads as enforced when it is not is worse than one that reads as a convention:

- The third rule's `Reason:` label is checked by `.github/tests/`: a disclosure carrying no label, or an empty one, fails.
- The second rule is asserted there only to be **stated** — that this text still says it. Whether an edit obeys it is not checkable, and a task deleted rather than disclosed is invisible to every check in this repository.
- The first rule is not machine-checked at all.

So two of the three end at a reviewer, and the wording below is what they review against.

**A change's `tasks.md` ends at the archive commit.** Branch and working-tree removal happen after the record's own pull request merges, which is after the commit that writes `tasks.md` — so a task for them can never be ticked in the file that contains them, and is unticked by construction forever. Record them in prose instead. This is narrow: the archive step itself belongs in `tasks.md` and is unaffected.

**An archived change's record may be corrected only to make it say what actually happened, with the evidence cited, and never to change what was decided or built.** Retroactive edits to an archived `tasks.md` are legitimate — a task performed but never ticked should be ticked — but only against evidence named in the record, and the tick itself SHALL be marked retroactive so it cannot be read as contemporaneous. Cite evidence that can still be checked: a figure another committed file records, a file's presence and date, an image digest or timestamp. Evidence that has already expired when it is written down is the thing this rule exists to prevent. This rule is also the only guard against a task being deleted rather than disclosed: no static check can see a line that is gone, so this is where that case is caught.

**A change directory with no deltas needs `skip_specs: true`, and that includes an opened handoff.** `openspec validate --all` runs on every pull request and fails a change carrying no specification deltas — *"Change must have at least one delta"*. Two states the workflow above prescribes hit this:

- **An opened change**, which is a branch and a `handoff.md` with no proposal. Give it an `.openspec.yaml` carrying `schema:`, `created:` and `skip_specs: true` at the moment it is opened, and drop the `skip_specs` line when its deltas are written. Without it, the branch cannot pass the required check.
- **A change genuinely declaring no deltas** — a refactor, a tooling or docs change. Four archived changes already use this; it is the established form, not a workaround.

`skip_specs: true` alone in the file is not enough: dropping `schema:` makes the change fail to resolve and the error is the same one, which reads as though the setting did not work.

**Work not performed is disclosed, not deleted and not ticked.** Put it under a `## Not performed` heading as a list item naming the task, with its reason on a following line introduced by a `Reason:` label. This covers work not performed for *any* reason — declined on judgment, unreachable in the authoring environment, or never captured and no longer recoverable. Ticking a box for work that was not done makes a ticked box mean either that the work happened or that it did not, which is no signal at all. The `Reason:` label is what the pipeline checks and it only checks for silence; whether the reason is a *good* one is a question for review.

### Namespacing Molecule per working tree

This is the binding the shared-service rule above promises. Molecule is the one
shared service this project's verification writes to, and it shares **two**
handles across every working tree on the machine, both stable per role:

- **The instance name**, a literal in each scenario's `platforms[].name`.
- **The ephemeral directory**, `$ANSIBLE_HOME/tmp/molecule.<id>.<scenario>`,
  whose `<id>` is a checksum of the role directory's **basename** rather than of
  its path — so it is identical across working trees by construction, and moving
  a working tree does not escape it.

`~/.cache/molecule/<role>` is **not** a third handle under the pinned
`molecule==26.8.0`, whatever an older note may say.

**Run the suite through `ansible/scripts/run-molecule`.** It derives this
working tree's namespace deterministically from the tree's own path, points
`ANSIBLE_HOME` at `.molecule-home/` inside the tree, and names the shared
`collections` path explicitly. `ansible/scripts/run-molecule --print-namespace`
computes it and runs nothing.

    ansible/scripts/run-molecule test --all      # from a role directory

`ANSIBLE_HOME` rather than `MOLECULE_EPHEMERAL_DIRECTORY`, and the difference
matters: the latter names *one* directory outright, with no per-scenario suffix,
so a single exported value collapses every scenario of every role into it —
reintroducing the shared state inside a single `molecule test --all`. The former
moves the tree and leaves the `molecule.<id>.<scenario>` split intact.

Collections are shared rather than namespaced, being read-only content pinned by
`ansible/requirements.yml`. They must be named explicitly all the same, because
relocating `ANSIBLE_HOME` relocates `$ANSIBLE_HOME/collections` with it. On a
machine that has never installed them, the entry point says so and stops; the
one-time install is `ansible-galaxy collection install -r
ansible/requirements.yml`, which is the manifest that pins them — naming the
collections individually would both miss `community.general`, which `hardening`
and `platform_data_volume` need at converge, and resolve floating versions this
project's own pinning rule forbids. Without that check the run fails deep inside `create` with
`couldn't resolve module/action 'community.docker.docker_login'`, which reads as
a broken mechanism rather than an unprovisioned machine.

**Bringing your namespace to the project's initial state**, which the rule above
requires as much as taking one: `ansible/scripts/run-molecule destroy --all`, run from each role
directory, removes this tree's containers — `--all` for the same reason it is
required above, since without it Molecule destroys only that role's `default`
scenario and leaves every sibling up; and its ephemeral directories are `.molecule-home/tmp/`
inside the tree — removable wholesale, since nothing outside the tree reads
them. Molecule does not clear that directory itself, even after a run that
exits 0, so a tree resumed after a crashed run starts from whatever the crash
left. Nothing reclaims the namespace of a working tree that has been removed;
its `.molecule-home/` goes with the tree, and any container it left is named
after it and can be removed by name.

**A run that supplies no namespace refuses.** Each scenario's name defaults to a
value carrying a colon, which Docker forbids in a container name, so `create`
fails and echoes the name back. That is deliberate and load-bearing: Molecule's
interpolator substitutes *empty* for an unset `${VAR}` and has no `:?` error
form, so without a refusing default a forgotten variable would silently restore
the shared name. `.github/tests` fails the build on a default Docker would
accept, and on a scenario whose name carries no namespace at all.

Each platform also declares an explicit short `hostname`. The driver otherwise
derives one from the instance name, and Linux caps a host name at 64 bytes — a
namespaced name crosses it on this repository's own working-tree names.

### Testing

There is no traditional unit-test layer for the Terraform code yet. Verification is static analysis (`terraform fmt`, `terraform validate`, `tflint`, Trivy, `gitleaks`) plus mandatory human review of an exact `terraform plan`.

This project has **three** test commands, and a change may owe tests under any of them. The independent-test-authoring step in the workflow above must be dispatched with the row that fits what the change touches — a dispatch carrying only the Terraform glob cannot place a test for anything else, and a test author who cannot place a file will report the gap rather than inventing a destination:

| Subject | Test command | Test-path glob |
|---|---|---|
| Terraform modules | `terraform test`, run from each module directory | `terraform/modules/<name>/tests/*.tftest.hcl` |
| The behaviour of an Ansible role on a host — what it converges to, and how it fails | `ansible/scripts/run-molecule test --all`, run from each role directory | `ansible/roles/<name>/molecule/<scenario>/` |
| Any property that is a static read of a committed file — CI configuration such as workflows, `dependabot.yml` and `.pre-commit-config.yaml`; static properties of what CI runs, such as the image pins in `ansible/roles/*/molecule/*/molecule.yml`; and repository-wide conventions such as the citation form below | `python3 -m unittest discover --start-directory .github/tests`, run from the repository root | `.github/tests/*.py` |

The `.github/tests` suite exists because `terraform test` can only exercise Terraform modules, so the guarantees this pipeline makes about its own configuration were unverifiable by anything the project had. Its dependencies are pinned in `.github/requirements-ci.txt`.

Its subject is deliberately wider than `.github/`, and wider than the pipeline: a property is in scope wherever the file holding it lives, so long as the assertion is a static read of a committed file. Most of what it asserts is something the pipeline depends on, but that is not the boundary — the suite is this repository's only mechanism that reads committed files at repository scope, so a convention that has to hold across the tree is asserted here or nowhere. What is *not* in scope is anything needing a network call, a credential, a container runtime or a Terraform binary — those constraints are themselves asserted by tests in that suite, and a check that cannot be written within them belongs somewhere else. **Those assertions currently read only `test_ci_configuration.py`, the module they live in**, so for any other module in the suite this is a convention a reviewer enforces rather than a check. `docs/change-queue.md` entry 45 covers widening them.

The Molecule row and the `.github/tests` row are near-opposites and are easy to confuse. Molecule asserts what a role *does* — it needs a container runtime and converges a real host, so it is the only place a role's failure path can be observed. `.github/tests` asserts what a committed file *says*, statically, and may not spawn a container at all. A property of a `molecule.yml` — its image pin — is therefore asserted by `.github/tests`, while the behaviour that scenario exercises is asserted by Molecule. Its toolchain is pinned in `ansible/requirements-test.txt`, and CI runs it as `ansible-verify.yml`.

Two things about `molecule test --all` that a verification claim depends on. It runs a role's scenarios in sorted order and **stops at the first failure**, so every scenario sorting after a failing one is silently not executed and not listed in the run's SCENARIO RECAP — read the recap and confirm it names every scenario the role has, rather than reading the exit code alone. While a role is red, run its scenarios individually with `ansible/scripts/run-molecule test -s <name>`. Molecule's own `--continue-on-failure` is not available here: it applies only with `--workers`, and `--workers > 1` requires collection mode (`galaxy.yml`), which these plain roles are not.

**Molecule's state is shared across working trees, and two of its handles are stable per role.** The instance name is a literal in each scenario's `platforms[].name`, so two working trees running the same role create, converge and destroy *the same container*. The ephemeral directory is `$ANSIBLE_HOME/tmp/molecule.<id>.<scenario>` (`~/.ansible/tmp/` by default), and `<id>` is a checksum of the role directory's **basename** rather than of its path — so it is identical across working trees by construction, and relocating a working tree does not escape it. Molecule does not remove that directory when a run finishes, so inheriting one another tree left behind is the default rather than the exception, and `flock` does not help: serialising two runs in time does nothing about a run inheriting a directory left earlier.

One cause, three presentations, which is what makes it read as three unrelated defects: a `create` that fails reading a `molecule.yml` a concurrent `destroy` has just pruned; a `prepare` whose container is torn down under a running play (`UNREACHABLE ... Failed to create temporary directory`); or a `verify` task dying with **rc 137** far into the run. The last is the one most often misread — what identifies it is the pairing of SIGKILL with **empty** stdout and stderr, which Ansible reports as `Module result deserialization failed: No start of json char found`. That reads like a module bug and is not one. `molecule test --all` compounds it, by the rule above: a collision in the first scenario leaves the rest neither executed nor listed. **The danger is not the red runs.** A colliding run can equally pass against a container the other session converged, which reads as evidence that the change under test is sound. These handles are namespaced per working tree — see *Namespacing Molecule per working tree* above, which is how you take yours. What is written here is what a run outside that mechanism still meets, and it is worth knowing rather than forgetting: a session's report that it left nothing behind is still worth checking against `docker ps` rather than believing.

### Citing this repository's own specifications and change records

A change's planning artifacts move when it is archived — from
`openspec/changes/<name>/` to `openspec/changes/archive/<date>-<name>/` — and the
archive date does not exist until archiving happens. A citation of the
pre-archive path therefore cannot be written correctly in advance, and breaks in
the same commit that proves the change worked. Cite by what you are pointing at:

| What you are citing | How to write it |
|---|---|
| A requirement | `openspec/specs/<capability>/spec.md`, plus the requirement's own name |
| Rationale or history that lives only inside a change — its `proposal.md`, `design.md`, `test-plan.md`, `test-manifest.md` | The change's name and the artifact's name, in prose, with no path |

Archiving merges a change's delta specifications into the main specification, so
the first form's path is permanent — and it names the requirement as it stands
now, rather than as one change once proposed it. The second form has no path to
break. Once a change is archived you may also give its location as
`openspec/changes/archive/<date>-<name>/…`, which is stable.

Do not write a path naming a change's own directory under `openspec/changes/`,
whether or not a further path component follows the change's name. Over a third
of the citations this rule replaced named the change and stopped there.

One interval is accepted. Where a change introduces a **new** capability,
archiving is what creates `openspec/specs/<capability>/spec.md`, so a citation of
it does not resolve until that change is archived. That is bounded by the
change's own life and is not rot.

`.github/tests/test_ci_configuration.py` asserts this, because no author or
reviewer can catch a violation: the citation is correct when written, correct
when reviewed, and wrong only once the change it cites has succeeded. The
previous sweep of these paths changed no rule and re-accumulated in three weeks.

### Development tooling

Run `pre-commit install --hook-type pre-commit --hook-type commit-msg` once per clone (see README's Local setup). It runs `terraform fmt`, `tflint`, `terraform validate`, `gitleaks`, `ansible-lint`, and `ansible-playbook --syntax-check` on `git commit`, and `commitlint` (Conventional Commits) on the commit message.

### Host configuration and platform stack

`ansible/` configures a Terraform-provisioned host; `platform/` holds the shared Compose stack every application on that host depends on. See `iac-host-configuration` and `iac-platform-services`, and `openspec/changes/archive/2026-08-19-integrate-ansible-host-config/design.md` for the full rationale. This project's defaults for the decisions those specs leave to the consuming project:

- **Inventory**: dynamic, via the `hcloud` plugin (`ansible/inventory/hcloud.yml`), grouped by the existing `environment` label — never a static or hand-maintained hosts file, so a disabled/destroyed server can't leave a stale entry behind.
- **Container runtime**: installed via a pinned external Galaxy role (`geerlingguy.docker`, pinned in `ansible/requirements.yml`) — not the only acceptable pattern going forward, but this project's current default. Any external role or collection used for any purpose is pinned to an exact version, never a floating range.
- **Secrets**: Ansible Vault is the default mechanism. Encrypting the *source* value isn't enough — a task that renders a Vault-decrypted value into an on-host file (e.g. an `.env` file) produces plaintext on disk regardless of how the source was protected. Any such rendered file must have restrictive permissions and must be excluded from version control.
- **Firewall split**: the Hetzner cloud firewall (Terraform-managed) is the default-deny gate for what's reachable from the internet at all; Ansible-managed UFW/fail2ban is host-level defense-in-depth on top of what the cloud firewall already allows. For any given port, exactly one layer is the documented access gate — never opened at only one layer while assumed closed at the other.
- **Scope boundary**: Ansible's responsibility ends once the container runtime is installed and ready. It never templates an application service-definition file (e.g. a Compose file) and never invokes a runtime's application-lifecycle commands (starting, stopping, restarting an application stack) — that's `platform/`'s and each application's own Compose files, deployed by a mechanism other than Ansible.
- **No dedicated monitoring server**: Prometheus and Grafana run alongside `platform/`'s stack on the same host rather than on a separate monitoring server; single-host observability risk is mitigated with an external dead-man's-switch, not a second server.
