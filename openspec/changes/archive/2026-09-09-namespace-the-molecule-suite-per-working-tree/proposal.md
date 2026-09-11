## Why

`AGENTS.md` states that where verification writes to a shared service, a session SHALL take its own namespace within it, named deterministically from its working tree — and that where this project binds that rule to a particular service, the binding is an adjacent section of the file. **No such section exists, for any service**, while Molecule is the one shared service this project's verification actually writes to. The rule is stated and nothing is bound to it.

Two of Molecule's handles are shared across every working tree on the machine and stable per role, so two sessions running one role drive the same container. The danger is not that such a run goes red. **A colliding run can equally pass**, against a container the other session converged — which reads as evidence that the change under test is sound. That is a verification result that means nothing, produced by a suite that reports success, which is the vacuous pass this repository refuses everywhere else.

This is not hypothetical and not rare. It cost two sessions time on 2026-09-07, presenting as three unrelated defects. `AGENTS.md`'s Testing section now *describes* the hazard, so a session can recognise it; nothing yet *removes* it, so coordination between sessions remains the whole safeguard. Three worktrees were live on this machine while this proposal was written.

## What Changes

- Every scenario this repository authors carries a **per-working-tree instance name**: `platforms[].name` gains a namespace component read from the environment, so two working trees running one role no longer name one container. Each platform also declares a short explicit `hostname`, because the container's hostname is otherwise derived from that name and is capped at 64 bytes — a limit this repository's own change names cross.
- That name's default is a **sentinel that is an invalid Docker container name**, so a run with no namespace set fails at `create` rather than silently reverting to the shared name. The instruction is carried in the sentinel text, so the error says what to set.
- The **ephemeral directory** is relocated per working tree via `ANSIBLE_HOME`, which preserves Molecule's own `molecule.<id>.<scenario>` split and therefore composes with `molecule test --all`.
- A **documented entry point** computes both values deterministically from the working tree and runs Molecule with them, so the correct invocation is the easy one rather than something each session reconstructs.
- `.github/tests` gains assertions that every authored scenario's name carries the namespace and the sentinel — a scenario added later cannot quietly opt out.
- `AGENTS.md` gains the **binding section** its shared-service rule has always promised, naming Molecule as the service and this mechanism as the binding.

No capability regresses and no scenario loses its name — each keeps its current name as the prefix of the new one. But **every existing invocation stops working the moment this merges**, locally and in continuous integration alike, until it supplies a namespace. That is the sentinel doing its job rather than an oversight: an invocation that kept working without one would be the fail-open this change exists to close.

## Capabilities

### New Capabilities

None. The obligation belongs to an existing capability whose stated purpose is local developer quality gates.

### Modified Capabilities

- `iac-repo-foundations`: ADDED requirement — verification that writes to state shared beyond the working tree SHALL namespace that state per working tree, and SHALL fail rather than proceed where the namespace is absent. This capability's purpose is "repo scaffolding and local developer quality gates", and this hazard is local: continuous-integration runners are isolated by construction and never observe it.
- `iac-cicd-pipeline`: MODIFIED requirement — *Ansible Configuration Is Verified in Continuous Integration and Gates the Merge* already obliges every authored scenario to declare a digest-pinned platform image, checked statically over `ansible/roles/*/molecule/*/molecule.yml`. The instance-name obligation is a static property of the same files, checked by the same suite, and belongs beside it rather than in a second mechanism.

## Impact

- **Every authored scenario definition** under `ansible/roles/*/molecule/*/molecule.yml` — two lines each, the namespaced `name` and the new `hostname`. The Galaxy-installed `geerlingguy.docker` scenario is excluded, as it already is from the digest-pin check, by the same manifest-derived rule.
- **`.github/tests/test_ci_configuration.py`** — new assertions over the same scenario files the pinning checks already read.
- **`AGENTS.md`** — a new binding section, adjacent to the shared-service rule.
- **A new entry point** for running the suite, and the provisioning step that makes a fresh working tree able to use it.
- **No production surface.** Nothing under `terraform/`, `platform/`, or any role's `tasks/` changes; no deploy is triggered and no host is touched.
- **Continuous integration is unaffected in behaviour**, each job being an isolated runner, but must keep passing: the sentinel means CI has to supply a namespace like any other caller.

### Consequences deliberately accepted

**Collections stay shared.** Relocating `ANSIBLE_HOME` also relocates `$ANSIBLE_HOME/collections`, which is where Molecule's docker driver finds `community.docker`. Left alone, a fresh namespace fails at `create` with `couldn't resolve module/action 'community.docker.docker_login'`. Collections are read-only content rather than run state, so they are shared rather than reinstalled per namespace. Design records the alternative.

**One handle is closed against a false pass, not against every write.** A run started with no namespace writes to the shared *ephemeral directory* before `create` reaches the container name and refuses. What this change closes is the failure that matters — a run reporting success against another session's container. What it leaves is a noisy failure, of the kind `AGENTS.md`'s Testing section already teaches a session to recognise. The requirement is written to that boundary rather than past it, and design records why the alternatives that would close it do not work.
