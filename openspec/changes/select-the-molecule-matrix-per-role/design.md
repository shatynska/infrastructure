## Context

See `proposal.md` — Why. What shapes the approach is three things the workflow already has, and one fact about the tree that had to be established rather than assumed.

The workflow's `discover` job runs on every pull request, resolves a `dorny/paths-filter` over `ansible/**` minus four exclusions, and emits two outputs: the roles it discovered and whether the suite is owed. The `molecule` matrix is gated on the job, never on its steps. The `ansible-verify` gate reads three inputs and refuses three ways — a discovery that did not succeed, a skip on a run that asked for the suite, and any other conclusion — which is what stops a skipped job being read as a passing one.

The fact that had to be established is the shape of the cross-role coupling. **Within the scenario directories it is entirely the converge graph**, and that much is machine-established: `PERMITTED_CONTROLLER_READS` in `.github/tests/test_ci_configuration.py` enumerates every controller-side read of a repository file across all seventeen authored scenarios, and no entry in it reads inside another role's directory — the role-local scans stay in their own role, the `import_playbook` chain is `platform_data_volume` reaching its own sibling scenario, and the one read escaping a role directory is `docker`'s scenario reading `ansible/requirements.yml`, a shared input that selects every role anyway.

**That evidence does not reach outside a scenario directory, and it is important not to read it as though it did.** `unpermitted_controller_reads` walks each scenario's own directory; it is silent about a role's `tasks/` or `handlers/` invoking another role, which is the same class of coupling that makes `meta/main.yml` worth reading at all. That case is closed separately, by refusal rather than by evidence — see Decision 2.

**The graph, swept from the tracked tree.** Scenarios of the left role converge the right:

| role | converges |
|---|---|
| `deploy_user` | `docker` (`default/converge.yml`, `ghcr-credential-rejected/converge.yml`) |
| `image_prune` | `docker` (`abandon-paths`, `default`, `heartbeat` converges) |
| `ops_user` | `docker`, `deploy_user` (`default/converge.yml`) |
| `docker`, `hardening`, `platform_data_volume`, `swap` | nothing outside themselves |

Reversed and closed, a diff touching `docker` owes `docker`, `deploy_user`, `image_prune` and `ops_user`; one touching `deploy_user` owes `deploy_user` and `ops_user`; every other role owes only itself.

That table is recorded for a reader, not for the implementation to consult. Nothing commits it.

## Goals / Non-Goals

**Goals:**

- A pull request confined to one role's directory starts the jobs that role's closure names, and no others.
- Every way the selection can be wrong resolves to running more rather than fewer.
- A selection that is empty where the suite was owed fails, rather than skipping into the gate's "correctly did no work" branch.
- The closure is checked statically, so that a scenario added later is covered without an edit to the check.

**Non-Goals:**

- Per-*scenario* selection. The unit is the role, which is what the matrix rows already are and what `molecule test --all` already takes.
- Selecting over anything but the suite tier. The lint tier stays triggered by the whole of `ansible/`.
- Reducing what a single job costs — see `proposal.md`'s Not in scope.

## Decisions

### Decision 1: Derive the graph at run time from scenario text, rather than committing it

A committed graph is a list, and a list that can go stale is the thing `narrow-the-molecule-trigger-to-what-it-reads` spent its Decision 2 arguing about. Worse here: a stale graph does not merely waste runner time, it **under-selects**, and under-selection is invisible — the gate sees a green matrix over the rows it was handed.

Derived from the scenarios in the checkout, the graph cannot disagree with them. The cost is that the derivation must be right, which is what Decision 2 and the static check are for.

*Alternative considered:* a committed `role-dependencies.yml` with a check asserting it matches the sweep. That is the same derivation plus a file to forget to regenerate; the check would be the real mechanism and the file decoration.

### Decision 2: Follow four constructions, and refuse an unrecognised one

The sweep that produced the table above found edges through two constructions. Two more exist in the tree and must be followed, because a construction not followed under-reads the graph:

- a play's `roles:` list, entries as bare strings or as mappings with `role:` or `name:`;
- `include_role` and `import_role`, bare and fully qualified, including inside `block`/`rescue`/`always`;
- `import_playbook`, which `platform_data_volume`'s reverse-order arm uses to build on its sibling — today within one role, but nothing makes it so;
- a role's own `meta/main.yml` `dependencies`, which `docker` uses. Its entry names the external Galaxy role rather than one of ours, so it contributes no edge today and would contribute one silently the day it did.

A construction the derivation has no rule for, naming something that resolves to a role, is **refused** rather than ignored — the polarity `unpermitted_controller_reads` already applies to routes, for the same reason: a route list goes stale exactly as a path list does, and an unrecognised construction ignored is a silent gap where one refused costs a visible edit.

**Two further routes reach a role, and both are refused rather than followed.** Refusal is the cheaper remedy in each case, and it is the trade this repository already makes for routes:

- **A role's own task or handler files reaching outside that role's directory.** Keyed on the artefact rather than on a role name, deliberately: `include_tasks: ../other_role/tasks/x.yml` names no role, so a refusal worded as "invoking another role" would not bite on it while coupling the two roles exactly as an invocation would. So the rule is any construction in a role's own task or handler file that reaches content outside that role's directory. This is the same class of coupling that makes `meta/main.yml` worth reading, so the boundary cannot be drawn at the scenario directory and called complete — the Context argument above rests on `unpermitted_controller_reads`, which walks only each scenario's own directory and is silent about this. **No role in this tree does it today**, verified over `ansible/roles/*/tasks/` and `ansible/roles/*/handlers/` for role invocations, path-based includes and any `../` at all, so refusing costs nothing now and costs one visible edit the day someone writes one. The derivation therefore reads those files — to refuse, not to follow.
- **A nested `ansible-playbook` naming its playbook by expression.** One exists: `ansible/roles/ops_user/molecule/revocation-steady-state/verify.yml` runs `ansible-playbook` over `{{ ops_user_nested_scenario_dir }}/converge.yml` through `ansible.builtin.command`. The path is not a literal, so the derivation cannot close over where it leads. Refusing it outright would turn the required check red on every pull request, so this instance is **permitted by an explicit entry** keyed on file, construction and resolved target — the shape `PERMITTED_CONTROLLER_READS` already uses for exactly this read, recorded there as `delegated-path` `expr:{{ ops_user_nested_scenario_dir }}/converge.yml`. A second such construction, anywhere, refuses until someone records why it is safe.

The handoff into this change warned that its author's first attempt matched `name: docker` in `molecule.yml` — the Docker *driver*, not the role — and produced a graph claiming six roles depend on `docker`. `molecule.yml`'s **contents** are never read by the derivation at all; only its path is, and only to identify the role a scenario belongs to.

### Decision 3: Attribute a changed path to a role by directory, and widen on anything else

A changed path selects role `R` where and only where it is under `ansible/roles/<R>/`. Everything else under `ansible/` selects **every** role.

Three consequences worth stating, because each is a case where the obvious rule is subtly wrong:

**The selection is the closure restricted to the discovered set.** That one sentence is what makes the three cases below consistent, and leaving it implicit is how a matrix ends up with a row for a role that has no scenarios to run. Attribution and the closure both range over role *directories*; only roles that carry scenarios can be executed, so the restriction happens once, after the closure and before the matrix.

*A property of the graph, not a rule to follow, recorded because it names when the above would need re-checking.* A scenario-derived edge originates in a role that by definition carries scenarios, so such edges can only ever place an unexecutable role in a closure as the attributed **seed**. A `meta/main.yml` edge need not: a role declaring no scenarios but depending on `S` is a non-seed member of `S`'s reverse closure with nothing to run. No role in this tree is one today — `docker`, `image_prune` and `swap` carry the only `meta/main.yml` files and all three have scenarios — but it is why the restriction ranges over the whole closure rather than over the seed, and why an implementer who optimises it to "restrict the seed, it is the only one that can fail" would be wrong. A later change that followed role-internal invocations rather than refusing them, or added any route contributing edges from roles without scenarios, would widen this further.

- **Attribution is to the directory name, not to the discovered set.** A path under `ansible/roles/foo/` where `foo` carries no scenarios of its own still selects `foo`'s closure — `foo` itself together with every role whose scenarios converge it, directly or transitively. The restriction above then drops `foo`, because there is nothing to run for it, and leaves the convergers. Attributing only to roles that carry scenarios would instead drop the diff before the closure ever ran, losing the convergers too, and an empty selection on an owed run is exactly what must never quietly happen.
- **A selection whose restriction is empty widens to every discovered role.** This is the third case, and it is evaluated **over the selection as a whole, not per attributed role** — the distinction decides a real diff and is therefore written rather than left to be inferred. A pull request touching `ansible/roles/tailscale/` alone widens, its selection being otherwise empty; one touching `tailscale` *and* `swap` runs `swap` alone. Nothing is lost by that: a role with no scenarios is unverifiable by this suite whether or not other roles run, so widening for it buys no coverage, and this change exists to run fewer jobs. The polarity argument does not reach here — it governs paths whose coverage consequence is *unknown*, and this one is known to be nil. What pays the legibility cost is Decision 5: the gate names the subset it ran, so a reader meeting `molecule (swap)` on a diff that also touched `tailscale` is told why. The tree contains the widening case's live instance: `ansible/roles/tailscale/` carries `tasks/` and `defaults/`, declares no scenarios, and is converged by nobody. Directory attribution succeeds, the closure is `{tailscale}`, and restricting it to the roles the run can execute leaves nothing. Narrowing there would hand the matrix an empty list, or a row for a role with no `molecule/` directory for `run-molecule test --all` to find — either way a legitimate pull request meets a required check its author cannot make green. Widening costs one full-suite run on a diff that today already causes one, and keeps Decision 4's empty-selection refusal meaning what it says. `tailscale` is named here rather than left to be re-derived as hypothetical; `docs/change-queue.md` entry 3b owns its having no scenario.
- **Anything else widens.** `ansible/requirements.yml`, `ansible/requirements-test.txt`, `ansible/scripts/run-molecule`, `ansible/ansible.cfg`, and any path this rule does not recognise — including one added under `ansible/` that nobody thought about. This is the exclusion-polarity argument transposed: wasteful, visible, and correctable in one line, against silent and green.

A base-image digest needs no rule of its own. It lives in a scenario's `molecule.yml`, under its role's directory, and attributes there like everything else that role owns. What makes a shared-image bump reach every role that shares it is the existing obligation that scenarios naming one image repository name one digest — not anything in this attribution.

*Alternative considered:* attributing the shared inputs explicitly and treating the residue as attributable to nothing. That inverts the polarity — an unrecognised path would select nothing — and is the same defect in a different spelling.

### Decision 4: Two refusals, not one, and the vacuity refusal stays on the unfiltered set

Discovery keeps its existing refusal: no role under `ansible/roles/` carries a `molecule/` directory, so the check that gates every merge has disappeared, so fail. **That refusal reads the unfiltered tree**, because it is a fact about the tree rather than about the diff. Moving it behind the selection would turn a vanished suite into a correct skip.

The selection adds a second: the suite is owed and the selected set is empty. That cannot arise from Decision 3's widening, which is exactly why it is worth refusing — if it ever fires, the derivation is broken and the run must say so rather than hand the matrix an empty list and let the gate read the resulting skip.

### Decision 5: The gate reads the selection, and its fourth state is a narrower success

`ansible-verify` gains one input — the selected set — and one branch. The existing three refusals are untouched:

| discovery | matrix | suite owed | conclusion |
|---|---|---|---|
| not success | any | any | **fail** — precondition did not hold |
| success | skipped | yes | **fail** — skipped on a run that asked for it |
| success | skipped | no | success, nothing the suite reads changed |
| success | success | yes | success, **naming the subset it ran** |
| success | success | no | **fail** — the matrix ran on a run that owed nothing |

The last row is new and is **not** reachable under the shape this change ships: the `molecule` job stays gated on `if: needs.discover.outputs.run-suite == 'true'`, and only the matrix expression changes, so a matrix cannot conclude success while `run-suite` is false. It is written as defence against a later edit keying that job's condition on the selection instead — at which point the two outputs could disagree, and a disagreement means the selection and the decision to run were computed from different things. Saying it is unreachable today is what stops a later reader either acting on a false claim or "fixing" the job condition to make the branch reachable.

Naming the subset in the success message is what makes a wrongly narrow run visible to a human reading the check, which is the only reader that can catch a graph defect the static check did not model.

### Decision 6: The selector lives under `ansible/scripts/`, not under `.github/`

A path under `ansible/` is a trigger under the existing filter, and an unattributable one under Decision 3 — so editing the selector runs the whole suite, which is the correct blast radius for a change to what the suite selects. Under `.github/` it would be neither: the suite's filter does not reach `.github/`, so a selector edit would change what every later pull request runs while running nothing itself.

It is a Python module rather than shell, because `.github/tests` must import the derivation to assert it, and because the YAML parsing in Decision 2 is not shell's work. Its toolchain is `.github/requirements-ci.txt`, already installed for the static suite.

### Decision 7: The changed-file list comes from the filter that already runs

`dorny/paths-filter` resolves the pull request's diff through the API — the checkout is shallow and carries no base to diff against — and its `list-files: json` output gives the files that matched, positives minus exclusions. That is precisely the input Decision 3 wants, and it is the mechanism already in the job rather than a second one.

On a `workflow_dispatch` there is no diff, the filter does not run, and `run-suite` is already forced true by the existing polarity branch; the selection is forced to every discovered role by the same branch, in the same place, so the two cannot drift.

## Risks / Trade-offs

**A construction carries a role name the derivation cannot resolve statically — a variable, a loop.** → Refuse, per Decision 2. A name that is not a literal is not a name this check can close over, and refusing is the safe answer. No scenario in the tree names a *role* this way today; one names a nested playbook's *path* by expression, which Decision 2 permits by an explicit entry rather than by widening the rule.

**The graph is right and the closure is computed wrongly.** → This is the failure mode with no natural signal, so the static check asserts the closure itself against a fixture graph with a known answer, not only the sweep that feeds it. A closure over the real tree is also asserted, so that the two cannot both be wrong in the same direction.

**The selection is correct and a human reads a narrow run as a broken one.** → The gate names the subset it ran and why, so the check's own output distinguishes "ran four of seven because `docker` changed" from "ran four of seven for no stated reason".

**A role is renamed.** → The diff carries both the old and the new directory, both attribute, and the closure covers both. No special case.

**The prize is smaller than the last change's.** → Stated in the queue entry and accepted. Of the last twenty merged pull requests, six touched `ansible/` and two touched a role, each touching exactly one; the common case this buys is seven jobs down to one, on the check that gates every merge.

## Open Questions

None. The two questions that would have changed the task breakdown are both answered rather than deferred: whether any scenario reads inside another role's directory, answered in Context by the existing permitted-reads table; and what happens to a role carrying neither scenarios nor convergers, answered by Decision 3's third case against `ansible/roles/tailscale/`, which is the tree's live instance rather than a hypothetical.
